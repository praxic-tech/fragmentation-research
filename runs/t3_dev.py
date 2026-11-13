"""
t3_dev.py — tier 3 development: score the dev pools, choose the decoder, export
the model (RUN_DECISIONS D19, "tier 3 design"). DISJOINT corpus only; the code
bundle this ships in contains no evaluation pool.

Stages (each skipped if its output exists):
  1. score   the same 46 dev pools tier 0 used (runs/t0_dev.make_pools), masked
             and shuffled exactly as the final runner does, every ordered pair
             through the trained model -> OUT/dev_scores/
  2. tune    on those matrices, CPU:
               orderer  in {borda, position, path1}, by mean within-document
                        Kendall tau over the dev pools' documents (true membership)
               grouper  in {agglo, spectral} x refine in {off, on}, by mean F1_L
               decoder  cluster-rank (chosen grouper + orderer) unless path-cover
                        has strictly higher mean F1_J
             Ties go to the first value listed. -> OUT/dev_tuning.json
  3. export  ONNX (opset 17, FP32) + parity check against torch on dev pairs,
             and RECORD.json with every hash. -> OUT/model/model.onnx

    python runs/t3_dev.py --data documents.jsonl --out OUT [--smoke]
"""

import argparse
import json
import os
import statistics
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
for d in ("adversaries", "harness", "analysis", "runs"):
    sys.path.insert(0, os.path.join(ROOT, d))

import numpy as np                                            # noqa: E402
from scipy.stats import kendalltau                           # noqa: E402

import crossenc_t3 as T3                                      # noqa: E402
import t0_dev as D0                                           # noqa: E402  (same dev pools, shown order, scorer)

SEED = 42
REFINES = (False, True)


def dev_pools(data, smoke):
    docs = D0.load(0) if data is None else [json.loads(l) for l in open(data, encoding="utf-8") if l.strip()]
    if smoke:
        docs = docs[:400]
        D0.N_POOLS = 3
    dev = [d for d in docs if D0.split_of(d["pmcid"]) == "dev"]
    return D0.make_pools(dev)


def unit_view(frags):
    shown, ms = D0.shown_and_seed(frags)
    ids, texts, back = T3.masked_view(shown, SEED, ms)
    return shown, ms, ids, texts, back


def stage_score(pools, out, device_name):
    import torch
    store = os.path.join(out, "dev_scores")
    todo = [(pid, frags) for pid, frags, _t in pools if T3.store_load(store, unit_view(frags)[3]) is None]
    if not todo:
        print("dev scores already complete", flush=True)
        return store
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = T3.load_model(os.path.join(out, "model")).to(device)
    tok = T3.load_tokenizer(os.path.join(out, "model"))
    infer = T3.torch_infer_fn(model, device)
    t0, n = time.time(), 0
    for pid, frags in todo:
        texts = unit_view(frags)[3]
        sc = T3.score_texts(texts, tok, infer)
        T3.store_save(store, texts, sc)
        n += sc["n_pairs_scored"]
        print(f"  scored {pid}: {len(texts)} fragments, {sc['n_pairs_scored']} pairs "
              f"({n / max(time.time() - t0, 1e-9):.0f} pairs/s)", flush=True)
    return store


def stage_tune(pools, store, out):
    units = []
    for pid, frags, truth in pools:
        shown, ms, ids, texts, back = unit_view(frags)
        sc = T3.store_load(store, texts)
        fwd = {v: i for i, v in enumerate(back[x] for x in ids)}      # raw id -> index
        units.append((pid, frags, truth, shown, ms, sc, fwd, len(truth)))

    # orderer: within-document tau, true membership
    ord_rows = []
    for how in T3.ORDERERS:
        taus = []
        for pid, frags, truth, shown, ms, sc, fwd, n in units:
            for rid, true_order in truth.items():
                idx = [fwd[f] for f in true_order]
                if len(idx) < 2:
                    continue
                got = T3.order_group(idx, sc, how)
                rank = {x: r for r, x in enumerate(got)}
                t = kendalltau([rank[x] for x in idx], np.arange(len(idx))).statistic
                if not np.isnan(t):
                    taus.append(t)
        ord_rows.append({"orderer": how, "mean_tau": statistics.fmean(taus), "n_docs": len(taus)})
        print(f"  orderer {how:<9} mean dev tau {ord_rows[-1]['mean_tau']:.4f}", flush=True)
    orderer = max(ord_rows, key=lambda r: (r["mean_tau"], -T3.ORDERERS.index(r["orderer"])))["orderer"]

    def run(cfg):
        rows = []
        for pid, frags, truth, shown, ms, sc, fwd, n in units:
            groups, _tel = T3.attack_from_scores(shown, n, store, cfg, seed=SEED, mask_seed=ms)
            rows.append(D0.score(pid, frags, truth, groups))
        return D0.summarise(rows)

    grid = []
    for g in T3.GROUPERS:
        for rf in REFINES:
            cfg = {"decoder": "cluster-rank", "grouper": g, "refine": rf, "orderer": orderer}
            s = run(cfg)
            grid.append({**cfg, **s})
            print(f"  cluster-rank {g:<8} refine {str(rf):<5}: F1_L {s['F1_L']:.4f}  F1_J {s['F1_J']:.4f}  "
                  f"q {s['q_micro']:.4f}", flush=True)
    best = max(grid, key=lambda r: (r["F1_L"], -T3.GROUPERS.index(r["grouper"]), -REFINES.index(r["refine"])))
    path = run({"decoder": "path-cover", "grouper": None, "refine": None, "orderer": None})
    print(f"  path-cover: F1_L {path['F1_L']:.4f}  F1_J {path['F1_J']:.4f}  q {path['q_micro']:.4f}", flush=True)
    if path["F1_J"] > best["F1_J"]:
        chosen = {"decoder": "path-cover", "grouper": None, "refine": None, "orderer": orderer}
        dev_scores = path
    else:
        chosen = {k: best[k] for k in ("decoder", "grouper", "refine", "orderer")}
        dev_scores = {k: best[k] for k in ("F1_J", "F1_L", "q_micro", "base", "exact_records")}
    res = {"orderer_grid": ord_rows, "chosen_orderer": orderer, "grouping_grid": grid, "path_cover_dev": path,
           "chosen": chosen, "dev_T3": dev_scores,
           "dev_pool_members": {pid: list(truth) for pid, _f, truth in pools},
           "dev_pools": len(pools), "dev_fragments": sum(len(p[1]) for p in pools)}
    t0p = os.path.join("results", "final_t0", "dev_tuning.json")
    if os.path.exists(t0p) and len(pools) == 46:
        same = json.load(open(t0p, encoding="utf-8"))["dev_pool_members"] == res["dev_pool_members"]
        res["same_dev_pools_as_tier0"] = same
        if not same:
            raise SystemExit("STOP: dev pools differ from tier 0's (results/final_t0/dev_tuning.json).")
    print(f"chosen: {chosen}", flush=True)
    return res


def stage_export(pools, out):
    import torch
    mdir = os.path.join(out, "model")
    onnx_p = os.path.join(mdir, "model.onnx")
    model = T3.load_model(mdir)
    tok = T3.load_tokenizer(mdir)
    texts = unit_view(pools[0][1])[3][:24]
    toks = T3.encode_fragments(tok, texts)
    ia = [toks[i] for i in range(len(toks)) for j in range(len(toks)) if i != j][:256]
    ib = [toks[j] for i in range(len(toks)) for j in range(len(toks)) if i != j][:256]
    ids, mask, types = T3.assemble(ia, ib, tok.cls_token_id, tok.sep_token_id, tok.pad_token_id)
    args = tuple(torch.from_numpy(x) for x in (ids, mask, types))
    if not os.path.exists(onnx_p):
        kw = dict(input_names=["input_ids", "attention_mask", "token_type_ids"], output_names=["out"],
                  dynamic_axes={k: {0: "batch", 1: "seq"} for k in ("input_ids", "attention_mask", "token_type_ids")}
                  | {"out": {0: "batch"}}, opset_version=17)
        tmp = onnx_p + ".tmp"
        try:
            torch.onnx.export(model, args, tmp, dynamo=False, **kw)
        except TypeError:
            torch.onnx.export(model, args, tmp, **kw)
        os.replace(tmp, onnx_p)
    with torch.no_grad():
        ref = model(*args).numpy()
    infer = T3.onnx_infer_fn(onnx_p, providers=["CPUExecutionProvider"])
    got = infer(ids, mask, types)
    short = infer(ids[:7, :], mask[:7, :], types[:7, :])              # other batch size
    diff = float(np.abs(ref - got).max())
    diff2 = float(np.abs(ref[:7] - short).max())
    # a different sequence length from the one the export was traced at
    k = np.argsort([len(x) + len(y) for x, y in zip(ia, ib)], kind="stable")[:16]
    ids3, mask3, types3 = T3.assemble([ia[i] for i in k], [ib[i] for i in k],
                                      tok.cls_token_id, tok.sep_token_id, tok.pad_token_id)
    with torch.no_grad():
        ref3 = model(*(torch.from_numpy(x) for x in (ids3, mask3, types3))).numpy()
    diff3 = float(np.abs(ref3 - infer(ids3, mask3, types3)).max())
    print(f"ONNX parity: max |torch - onnx| = {diff:.2e} (batch 256, len {ids.shape[1]}), {diff2:.2e} (batch 7), "
          f"{diff3:.2e} (batch 16, len {ids3.shape[1]})", flush=True)
    diff2 = max(diff2, diff3)
    if max(diff, diff2) > 1e-3:
        raise SystemExit("STOP: ONNX export does not reproduce the torch model.")
    return {"onnx_sha256": T3.file_sha256(onnx_p), "onnx_parity_max_abs_diff": max(diff, diff2),
            "onnx_opset": 17, "onnxruntime": __import__("onnxruntime").__version__}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=None)
    ap.add_argument("--out", required=True)
    ap.add_argument("--smoke", action="store_true")
    a = ap.parse_args()
    out = os.path.abspath(a.out)
    if not os.path.exists(os.path.join(out, "TRAIN_DONE.json")):
        raise SystemExit("training has not finished (no TRAIN_DONE.json)")
    train_rec = json.load(open(os.path.join(out, "train_log.json"), encoding="utf-8"))
    mdir = os.path.join(out, "model")
    sha = T3.file_sha256(os.path.join(mdir, "pair_model.safetensors"))
    if sha != train_rec["model_sha256"]:
        raise SystemExit("STOP: model file does not match train_log.json")

    pools = dev_pools(a.data, a.smoke)
    print(f"{len(pools)} dev pools, {sum(len(p[1]) for p in pools)} fragments", flush=True)
    t0 = time.time()
    store = stage_score(pools, out, None)
    tune_p = os.path.join(out, "dev_tuning.json")
    if os.path.exists(tune_p):
        tune = json.load(open(tune_p, encoding="utf-8"))
        print("dev tuning already done:", tune["chosen"], flush=True)
    else:
        tune = stage_tune(pools, store, out)
        tune["model_sha256"] = sha
        json.dump(tune, open(tune_p, "w", encoding="utf-8"), indent=1)
    exp = stage_export(pools, out)
    rec = {"model_sha256": sha, **exp,
           "tokenizer_sha256": {f: T3.file_sha256(os.path.join(mdir, f)) for f in sorted(os.listdir(mdir))
                                if f in ("vocab.txt", "tokenizer.json", "tokenizer_config.json")},
           "base_model": T3.MODEL_NAME, "base_revision": T3.MODEL_REV,
           "data_sha256": train_rec["data_sha256"], "chosen": tune["chosen"], "dev_T3": tune["dev_T3"],
           "bundle_commit": open(os.path.join(ROOT, "BUNDLE_COMMIT.txt")).read().strip()
           if os.path.exists(os.path.join(ROOT, "BUNDLE_COMMIT.txt")) else None,
           "train": {k: v for k, v in train_rec.items() if k != "log"},
           "dev_seconds": round(time.time() - t0)}
    json.dump(rec, open(os.path.join(out, "RECORD.json"), "w", encoding="utf-8"), indent=1)
    print("RECORD.json written")
    print(json.dumps({k: rec[k] for k in ("model_sha256", "onnx_sha256", "chosen", "dev_T3")}, indent=1), flush=True)


if __name__ == "__main__":
    main()
