"""
t3_train.py — fine-tune the tier 3 cross-encoder on the DISJOINT corpus only
(RUN_DECISIONS D19, "tier 3 design"). Runs on a GPU (Colab); never reads an
evaluation pool, and the code bundle it ships in contains none.

One training run, fixed settings, no model selection: 2 epochs, AdamW 2e-5,
batch 128, seed 42. The model after the last step is the model.

Pairs, regenerated each epoch from seed + epoch (so a resumed run sees the same
data order). For every train sentence A, four pairs:
    near   a same-document sentence 1 away (p = 1/2) or 2-4 away
    far    a uniformly random other sentence of the same document
    2 x    a uniformly random sentence of another train document
each presented in a random order (A first or second).

Checkpoints go to --out every --ckpt-min minutes and at each epoch end;
restarting the same command resumes.

    python runs/t3_train.py --data documents.jsonl --out OUT [--smoke]
"""

import argparse
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for d in ("adversaries", "harness", "analysis", "runs"):
    sys.path.insert(0, os.path.join(ROOT, d))

import numpy as np                                            # noqa: E402

import crossenc_t3 as T3                                      # noqa: E402

SEED = 42
EPOCHS, BATCH, LR, WD, WARMUP, CLIP, POS_WEIGHT = 2, 128, 2e-5, 0.01, 0.06, 1.0, 4.0
CHUNK_BATCHES = 64        # batches are length-sorted inside chunks of this many


def split_of(pmcid):          # same rule as runs/t0_dev.py (not imported: that pulls in the scorer)
    import hashlib
    return "dev" if int(hashlib.sha256(pmcid.encode()).hexdigest(), 16) % 10 == 0 else "train"


def load_docs(path, max_docs=0):
    docs = []
    for line in open(path, encoding="utf-8"):
        if line.strip():
            docs.append(json.loads(line))
            if max_docs and len(docs) >= max_docs:
                break
    return docs


class Corpus:
    """Flat sentence table for one split: tokens, document id, position."""

    def __init__(self, docs, tokenizer):
        sents = [s for d in docs for s in d["sentences"]]
        self.tok = T3.encode_fragments(tokenizer, sents)
        self.len = np.array([len(t) for t in self.tok])
        n = np.array([len(d["sentences"]) for d in docs])
        self.doc = np.repeat(np.arange(len(docs)), n)
        self.start = np.repeat(np.cumsum(n) - n, n)
        self.n = np.repeat(n, n)
        self.i = np.arange(len(sents)) - self.start
        self.total = len(sents)


def epoch_pairs(c, rng):
    """(first, second, same, prec, adj, posFirst, posSecond) arrays, shuffled."""
    T, i, n = c.total, c.i, c.n
    k = np.where(rng.random(T) < 0.5, 1, rng.integers(2, 5, T))
    sign = np.where(rng.random(T) < 0.5, 1, -1)
    j = i + sign * k
    bad = (j < 0) | (j >= n)
    j = np.where(bad, i - sign * k, j)
    j = np.clip(j, 0, n - 1)
    j = np.where(j == i, np.where(i + 1 < n, i + 1, i - 1), j)
    near = c.start + j
    f = rng.integers(0, n - 1)
    far = c.start + np.where(f >= i, f + 1, f)
    negs = []
    for _ in range(2):
        g = rng.integers(0, T, T)
        for _try in range(8):
            clash = c.doc[g] == c.doc
            if not clash.any():
                break
            g = np.where(clash, rng.integers(0, T, T), g)
        negs.append(g)
    a = np.tile(np.arange(T), 4)
    b = np.concatenate([near, far] + negs)
    flip = rng.random(len(a)) < 0.5
    first, second = np.where(flip, b, a), np.where(flip, a, b)
    same = c.doc[first] == c.doc[second]
    prec = same & (c.i[first] < c.i[second])
    adj = same & (second == first + 1)
    pos = lambda x: c.i[x] / np.maximum(c.n[x] - 1, 1)        # noqa: E731
    perm = rng.permutation(len(a))
    return tuple(x[perm] for x in (first, second, same, prec, adj, pos(first), pos(second)))


def batches(c, pairs, rng):
    """Batch index arrays: length-sorted within chunks, chunk-internal order shuffled."""
    first, second = pairs[0], pairs[1]
    L = c.len[first] + c.len[second]
    out = []
    step = BATCH * CHUNK_BATCHES
    for s in range(0, len(first), step):
        idx = np.arange(s, min(s + step, len(first)))
        idx = idx[np.argsort(L[idx], kind="stable")]
        bs = [idx[t:t + BATCH] for t in range(0, len(idx), BATCH)]
        for t in rng.permutation(len(bs)):
            out.append(bs[t])
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--ckpt-min", type=float, default=20.0)
    ap.add_argument("--smoke", action="store_true", help="tiny random model, few documents, few steps")
    ap.add_argument("--max-docs", type=int, default=0)
    ap.add_argument("--max-steps", type=int, default=0)
    ap.add_argument("--smoke-lr", type=float, default=0.0, help="smoke runs only: override the learning rate")
    a = ap.parse_args()

    import torch
    os.makedirs(a.out, exist_ok=True)
    done_p = os.path.join(a.out, "TRAIN_DONE.json")
    if os.path.exists(done_p):
        print("training already complete:", open(done_p).read())
        return

    if not a.smoke:
        got = T3.file_sha256(a.data)
        if got != T3.DATA_SHA256:
            raise SystemExit(f"STOP: {a.data} sha256 {got} is not the corpus recorded in D19 ({T3.DATA_SHA256}).")
        print("corpus sha256 verified", flush=True)
    docs = load_docs(a.data, a.max_docs or (400 if a.smoke else 0))
    train = [d for d in docs if split_of(d["pmcid"]) == "train"]
    dev = [d for d in docs if split_of(d["pmcid"]) == "dev"]
    print(f"{len(docs)} documents: {len(train)} train, {len(dev)} dev", flush=True)

    torch.manual_seed(SEED)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    gpu = torch.cuda.get_device_name(0) if device.type == "cuda" else "cpu"
    print("device:", gpu, flush=True)
    tokenizer = T3.load_tokenizer()
    t0 = time.time()
    ctr, cdev = Corpus(train, tokenizer), Corpus(dev, tokenizer)
    print(f"tokenised {ctr.total} train + {cdev.total} dev sentences ({time.time() - t0:.0f}s); "
          f"mean {ctr.len.mean():.1f} word pieces, {100 * (ctr.len >= T3.SIDE_CAP).mean():.2f}% at the cap", flush=True)

    model = T3.new_model(smoke=a.smoke).to(device)
    decay, no_decay = [], []
    for name, p in model.named_parameters():
        (no_decay if p.ndim < 2 or "LayerNorm" in name else decay).append(p)
    opt = torch.optim.AdamW([{"params": decay, "weight_decay": WD}, {"params": no_decay, "weight_decay": 0.0}], lr=a.smoke_lr if (a.smoke and a.smoke_lr) else LR)
    steps_per_epoch = int(np.ceil(4 * ctr.total / BATCH))
    total_steps = steps_per_epoch * EPOCHS
    warm = int(WARMUP * total_steps)
    sched = torch.optim.lr_scheduler.LambdaLR(
        opt, lambda s: (s + 1) / warm if s < warm else max(0.0, (total_steps - s) / max(1, total_steps - warm)))
    amp = device.type == "cuda"
    scaler = torch.amp.GradScaler("cuda", enabled=amp)
    bce = torch.nn.functional.binary_cross_entropy_with_logits
    cls_id, sep_id, pad_id = tokenizer.cls_token_id, tokenizer.sep_token_id, tokenizer.pad_token_id

    def to_batch(c, pairs, idx):
        ids, mask, types = T3.assemble([c.tok[k] for k in pairs[0][idx]], [c.tok[k] for k in pairs[1][idx]],
                                       cls_id, sep_id, pad_id)
        tt = lambda x, dt=torch.float32: torch.as_tensor(np.asarray(x), dtype=dt, device=device)   # noqa: E731
        return (tt(ids, torch.long), tt(mask, torch.long), tt(types, torch.long), tt(pairs[2][idx]),
                tt(pairs[3][idx]), tt(pairs[4][idx]), tt(np.stack([pairs[5][idx], pairs[6][idx]], 1)))

    def losses(out, same, prec, adj, pos):
        l_same = bce(out[:, T3.I_SAME], same)
        w = same.sum().clamp(min=1.0)
        l_prec = (bce(out[:, T3.I_PREC], prec, reduction="none") * same).sum() / w
        l_adj = bce(out[:, T3.I_ADJ], adj)
        l_pos = torch.nn.functional.mse_loss(torch.sigmoid(out[:, T3.I_POSA:]), pos)
        return l_same + l_prec + l_adj + POS_WEIGHT * l_pos, (l_same, l_prec, l_adj, l_pos)

    dev_pairs = epoch_pairs(cdev, np.random.default_rng(SEED + 999))
    dev_idx = [np.arange(s, min(s + 256, 20000, len(dev_pairs[0]))) for s in range(0, min(20000, len(dev_pairs[0])), 256)]

    def dev_check():
        model.eval()
        ok_s = ok_p = n_s = n_p = 0
        se = 0.0
        with torch.no_grad(), torch.autocast(device_type=device.type, enabled=amp):
            for idx in dev_idx:
                ids, mask, types, same, prec, adj, pos = to_batch(cdev, dev_pairs, idx)
                out = model(ids, mask, types).float()
                ok_s += ((out[:, T3.I_SAME] > 0) == (same > 0.5)).sum().item()
                n_s += len(idx)
                sel = same > 0.5
                ok_p += ((out[sel, T3.I_PREC] > 0) == (prec[sel] > 0.5)).sum().item()
                n_p += int(sel.sum().item())
                se += ((torch.sigmoid(out[:, T3.I_POSA:]) - pos) ** 2).sum().item()
        model.train()
        return {"same_acc": ok_s / n_s, "precedes_acc": ok_p / max(n_p, 1), "pos_rmse": (se / (2 * n_s)) ** 0.5,
                "pairs": n_s}

    ck_p = os.path.join(a.out, "ckpt_last.pt")
    state = {"epoch": 0, "step_in_epoch": 0, "global_step": 0, "log": [], "resumes": 0, "train_seconds": 0.0}
    if os.path.exists(ck_p):
        ck = torch.load(ck_p, map_location=device, weights_only=False)
        model.load_state_dict(ck["model"])
        opt.load_state_dict(ck["opt"])
        sched.load_state_dict(ck["sched"])
        scaler.load_state_dict(ck["scaler"])
        state = ck["state"]
        state["resumes"] += 1
        print(f"resumed at epoch {state['epoch']} step {state['step_in_epoch']} (global {state['global_step']})", flush=True)

    def save_ckpt():
        tmp = ck_p + ".tmp"
        torch.save({"model": model.state_dict(), "opt": opt.state_dict(), "sched": sched.state_dict(),
                    "scaler": scaler.state_dict(), "state": state}, tmp)
        os.replace(tmp, ck_p)

    model.train()
    last_ck = t_run = time.time()
    stop = False
    for epoch in range(state["epoch"], EPOCHS):
        rng = np.random.default_rng(SEED + epoch)
        pairs = epoch_pairs(ctr, rng)
        bl = batches(ctr, pairs, rng)
        assert len(bl) == steps_per_epoch, (len(bl), steps_per_epoch)
        run = np.zeros(5)
        seen = 0
        for s in range(state["step_in_epoch"], len(bl)):
            ids, mask, types, same, prec, adj, pos = to_batch(ctr, pairs, bl[s])
            with torch.autocast(device_type=device.type, enabled=amp):
                out = model(ids, mask, types)
            loss, parts = losses(out.float(), same, prec, adj, pos)
            opt.zero_grad(set_to_none=True)
            scaler.scale(loss).backward()
            scaler.unscale_(opt)
            torch.nn.utils.clip_grad_norm_(model.parameters(), CLIP)
            scaler.step(opt)
            scaler.update()
            sched.step()
            state["step_in_epoch"], state["global_step"] = s + 1, state["global_step"] + 1
            run += np.array([loss.item()] + [p.item() for p in parts])
            seen += 1
            if state["global_step"] % 100 == 0 or s + 1 == len(bl):
                el = time.time() - t_run
                done_steps = state["global_step"]
                its = seen / max(el, 1e-9)
                eta = (total_steps - done_steps) / max(its, 1e-9) / 60
                row = {"step": done_steps, "epoch": epoch, "loss": run[0] / seen, "same": run[1] / seen,
                       "prec": run[2] / seen, "adj": run[3] / seen, "pos_mse": run[4] / seen,
                       "it_s": round(its, 2), "eta_min": round(eta, 1)}
                state["log"].append(row)
                print(f"step {done_steps}/{total_steps} ep {epoch} loss {row['loss']:.4f} "
                      f"(same {row['same']:.3f} prec {row['prec']:.3f} adj {row['adj']:.3f} pos {row['pos_mse']:.4f}) "
                      f"{its:.1f} it/s eta {eta:.0f} min", flush=True)
                run[:] = 0
                seen = 0
                t_run = time.time()
            if time.time() - last_ck > a.ckpt_min * 60:
                save_ckpt()
                last_ck = time.time()
                print("  checkpoint saved", flush=True)
            if a.max_steps and state["global_step"] >= a.max_steps:
                stop = True
                break
        if stop:
            save_ckpt()
            print("stopped at --max-steps (checkpoint saved)", flush=True)
            return
        chk = dev_check()
        print(f"epoch {epoch} done; dev pair check {chk}", flush=True)
        state["log"].append({"epoch_end": epoch, **chk})
        state["epoch"], state["step_in_epoch"] = epoch + 1, 0
        save_ckpt()
        last_ck = time.time()

    model.eval()
    mdir = os.path.join(a.out, "model")
    T3.save_model(model, tokenizer, mdir)
    rec = {"model_sha256": T3.file_sha256(os.path.join(mdir, "pair_model.safetensors")),
           "base_model": T3.MODEL_NAME, "base_revision": T3.MODEL_REV, "smoke": a.smoke,
           "data_sha256": None if a.smoke else T3.DATA_SHA256,
           "train_documents": len(train), "dev_documents": len(dev), "train_sentences": int(ctr.total),
           "pairs_per_epoch": int(4 * ctr.total), "epochs": EPOCHS, "batch": BATCH, "lr": LR, "weight_decay": WD,
           "warmup_share": WARMUP, "grad_clip": CLIP, "pos_weight": POS_WEIGHT, "side_cap": T3.SIDE_CAP,
           "seed": SEED, "steps": state["global_step"], "resumes": state["resumes"], "gpu": gpu,
           "torch": torch.__version__, "transformers": __import__("transformers").__version__,
           "final_dev_pair_check": [r for r in state["log"] if "epoch_end" in r][-1],
           "log": state["log"]}
    json.dump(rec, open(os.path.join(a.out, "train_log.json"), "w", encoding="utf-8"), indent=1)
    json.dump({k: rec[k] for k in ("model_sha256", "steps", "resumes", "gpu")}, open(done_p, "w", encoding="utf-8"))
    print(f"training complete: {state['global_step']} steps; model sha256 {rec['model_sha256']}", flush=True)


if __name__ == "__main__":
    main()
