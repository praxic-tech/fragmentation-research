"""
t3_score_eval.py — pair scores for every tier 3 evaluation unit (RUN_DECISIONS
D19, "tier 3 tuning, fixed before the evaluation run"). GPU; run on Colab.

Refuses to start unless the weights and tokenizer files hash to the values
committed in that addendum (EXPECT below). Scores each unit's texts, in the
order runs/t3_units.py gives them, with the same code dev tuning used
(crossenc_t3.score_texts + torch_infer_fn: torch, CUDA mixed precision), into
the score store under --out. Resumable: a unit already in the store is skipped
(the model and inputs are fixed). No decoding, no truth, no scores of
reconstructions happen here.

    python runs/t3_score_eval.py --model DIR --out DIR
"""

import argparse
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "runs"))
import t3_units as U                                           # noqa: E402
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
    print("weights and tokenizer match the committed hashes", flush=True)

    import torch
    if not torch.cuda.is_available():
        raise SystemExit("STOP: no GPU (Runtime > Change runtime type > GPU)")
    device = torch.device("cuda")
    gpu = torch.cuda.get_device_name(0)
    model = T3.load_model(a.model).to(device)
    tok = T3.load_tokenizer(a.model)
    infer = T3.torch_infer_fn(model, device)

    units = U.all_unit_texts()
    if a.limit:
        units = units[:a.limit]
    store = os.path.join(a.out, "eval_scores")
    os.makedirs(store, exist_ok=True)
    print(f"{len(units)} units on {gpu}, torch {torch.__version__}", flush=True)
    t0, pairs, done, skipped = time.time(), 0, 0, 0
    manifest = []
    for kind, game, cell, uid, texts in units:
        sha = T3.texts_sha(texts)
        if T3.store_load(store, texts) is None:
            sc = T3.score_texts(texts, tok, infer)
            T3.store_save(store, texts, sc)
            pairs += sc["n_pairs_scored"]
            done += 1
            if done % 10 == 0:
                el = time.time() - t0
                print(f"  {done + skipped}/{len(units)} units, {pairs:,} pairs, {pairs / el:,.0f} pairs/s, "
                      f"{el / 60:.1f} min", flush=True)
        else:
            skipped += 1
        manifest.append({"kind": kind, "game": game, "cell": cell, "unit": uid, "n": len(texts),
                         "texts_sha256": sha,
                         "file_sha256": T3.file_sha256(T3.store_path(store, sha))})
    rec = {"units": len(units), "scored_this_session": done, "already_present": skipped,
           "pairs_this_session": pairs, "minutes_this_session": round((time.time() - t0) / 60, 1),
           "gpu": gpu, "torch": torch.__version__, "precision": "torch CUDA autocast (fp16), as dev tuning",
           "weights_sha256": EXPECT["pair_model.safetensors"], "limit": a.limit, "manifest": manifest}
    name = "SCORE_SMOKE.json" if a.limit else "SCORE_DONE.json"
    json.dump(rec, open(os.path.join(a.out, name), "w", encoding="utf-8"), indent=1)
    print(f"{name} written: {len(units)} units, {done} scored now, {skipped} already present", flush=True)


if __name__ == "__main__":
    main()
