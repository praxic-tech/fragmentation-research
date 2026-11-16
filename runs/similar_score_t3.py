"""
similar_score_t3.py — tier 3 pair scores for the similar pools (RUN_DECISIONS
D20, POST-HOC EXPLORATORY). GPU; run on Colab from the similar-pools bundle.

runs/t3_score_eval.py with one change: the units come from the bundle's
texts.jsonl (checked against BUNDLE.json) instead of runs/t3_units.py. Same
frozen weights and tokenizer (hashes checked before anything runs), same
scoring code (crossenc_t3.score_texts + torch_infer_fn, CUDA mixed precision).
Resumable. No decoding, no truth.

    python runs/similar_score_t3.py --model DIR --out DIR
"""

import argparse
import hashlib
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for d in ("adversaries", "harness"):
    sys.path.insert(0, os.path.join(ROOT, d))
import crossenc_t3 as T3                                       # noqa: E402

EXPECT = {"pair_model.safetensors": "de081db6893e57ebc69b2cbb202851558f49b7d41eea38dc2c77ba73e947582a",
          "tokenizer.json": "65809d83aaf2d4270a0f24740da74c9c0f09ac67f1401708367697b57fb03df9",
          "tokenizer_config.json": "9f0c2c65a70ea18113ffa2e717103e7210ea826e7acc3442b69b346686b55a48"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--limit", type=int, default=0, help="score only the first N units (smoke test)")
    a = ap.parse_args()
    for f, want in EXPECT.items():
        got = T3.file_sha256(os.path.join(a.model, f))
        if got != want:
            raise SystemExit(f"STOP: {f} hashes to {got}, not the committed {want}")
    tp = os.path.join(ROOT, "texts.jsonl")
    want = json.load(open(os.path.join(ROOT, "BUNDLE.json"), encoding="utf-8"))["texts_sha256"]
    got = hashlib.sha256(open(tp, "rb").read()).hexdigest()
    if got != want:
        raise SystemExit(f"STOP: texts.jsonl hashes to {got}, not {want}")
    units = [json.loads(l) for l in open(tp, encoding="utf-8") if l.strip()]
    if a.limit:
        units = units[:a.limit]
    print("weights, tokenizer and texts match their recorded hashes", flush=True)

    import torch
    if not torch.cuda.is_available():
        raise SystemExit("STOP: no GPU (Runtime > Change runtime type > GPU)")
    device = torch.device("cuda")
    gpu = torch.cuda.get_device_name(0)
    model = T3.load_model(a.model).to(device)
    tok = T3.load_tokenizer(a.model)
    infer = T3.torch_infer_fn(model, device)

    out = os.path.join(a.out, "T3")
    store = os.path.join(out, "scores")
    os.makedirs(store, exist_ok=True)
    print(f"T3: {len(units)} units on {gpu}, torch {torch.__version__}", flush=True)
    t0, pairs, done, skipped, manifest = time.time(), 0, 0, 0, []
    for u in units:
        texts = u["texts"]
        sha = T3.texts_sha(texts)
        if T3.store_load(store, texts) is None:
            sc = T3.score_texts(texts, tok, infer)
            T3.store_save(store, texts, sc)
            pairs += sc["n_pairs_scored"]
            done += 1
            el = time.time() - t0
            print(f"  {done + skipped}/{len(units)} {u['unit']}: {len(texts)} frags; {pairs:,} pairs, "
                  f"{pairs / el:,.0f} pairs/s, {el / 60:.1f} min", flush=True)
        else:
            skipped += 1
        manifest.append({"kind": u["kind"], "game": u["game"], "unit": u["unit"], "n": len(texts),
                         "texts_sha256": sha, "file_sha256": T3.file_sha256(T3.store_path(store, sha))})
    rec = {"tier": "T3", "units": len(units), "scored_this_session": done, "already_present": skipped,
           "pairs_this_session": pairs, "minutes_this_session": round((time.time() - t0) / 60, 1),
           "gpu": gpu, "torch": torch.__version__, "precision": "torch CUDA autocast (fp16), as dev tuning",
           "weights_sha256": EXPECT["pair_model.safetensors"], "texts_sha256": got, "limit": a.limit,
           "manifest": manifest}
    name = "SCORE_SMOKE.json" if a.limit else "SCORE_DONE.json"
    json.dump(rec, open(os.path.join(out, name), "w", encoding="utf-8"), indent=1)
    print(f"T3 {name} written: {len(units)} units, {done} scored now, {skipped} already present", flush=True)


if __name__ == "__main__":
    main()
