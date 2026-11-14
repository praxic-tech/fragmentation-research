"""
t12_score.py — pair scores for tiers 1 and 2 (RUN_DECISIONS D19, "tiers 1 and 2
design"). GPU; run on Colab from the bundle runs/t12_make_bundle.py builds.

Reads texts.jsonl (every dev unit and every evaluation unit: kind, game, unit,
texts; no id, label or truth) and checks its SHA-256 against BUNDLE.json.
Loads the pinned model revision, scores every unit's texts with
lm_pmi_t12.score_texts into OUT/<tier>/scores (tier 3's store layout), dev
units first. Resumable: a unit already in the store is skipped. No decoding
and no truth happen here; the decoder is chosen afterwards, on CPU, from the
dev scores only.

    python runs/t12_score.py --tier T1 --out DIR [--limit N]
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
import lm_pmi_t12 as L                                         # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tier", choices=sorted(L.MODELS), required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--limit", type=int, default=0, help="score only the first N units (smoke test)")
    a = ap.parse_args()
    tp = os.path.join(ROOT, "texts.jsonl")
    want = json.load(open(os.path.join(ROOT, "BUNDLE.json"), encoding="utf-8"))["texts_sha256"]
    got = hashlib.sha256(open(tp, "rb").read()).hexdigest()
    if got != want:
        raise SystemExit(f"STOP: texts.jsonl hashes to {got}, not {want}")
    units = [json.loads(l) for l in open(tp, encoding="utf-8") if l.strip()]
    if a.limit:
        units = units[:a.limit]

    import torch
    import transformers
    if not torch.cuda.is_available():
        raise SystemExit("STOP: no GPU (Runtime > Change runtime type > GPU)")
    device = torch.device("cuda")
    gpu = torch.cuda.get_device_name(0)
    model, tok = L.load(a.tier, device, dtype=torch.bfloat16)
    name, rev = L.MODELS[a.tier]
    out = os.path.join(a.out, a.tier)
    store = os.path.join(out, "scores")
    os.makedirs(store, exist_ok=True)
    print(f"{a.tier} {name}@{rev[:12]}: {len(units)} units on {gpu}, torch {torch.__version__}", flush=True)
    t0, pairs, done, skipped, manifest = time.time(), 0, 0, 0, []
    for u in units:
        texts = u["texts"]
        sha = T3.texts_sha(texts)
        if T3.store_load(store, texts) is None:
            sc = L.score_texts(texts, model, tok, device)
            L.store_save(store, texts, sc)
            pairs += sc["n_pairs_scored"]
            done += 1
            el = time.time() - t0
            print(f"  {done + skipped}/{len(units)} {u['kind']} {u['game']} {u['unit']}: {len(texts)} frags; "
                  f"{pairs:,} pairs, {pairs / el:,.0f} pairs/s, {el / 60:.1f} min", flush=True)
        else:
            skipped += 1
        manifest.append({"kind": u["kind"], "game": u["game"], "unit": u["unit"], "n": len(texts),
                         "texts_sha256": sha, "file_sha256": T3.file_sha256(T3.store_path(store, sha))})
    rec = {"tier": a.tier, "model": name, "revision": rev, "units": len(units), "scored_this_session": done,
           "already_present": skipped, "pairs_this_session": pairs,
           "minutes_this_session": round((time.time() - t0) / 60, 1), "gpu": gpu, "torch": torch.__version__,
           "transformers": transformers.__version__, "precision": "bfloat16 weights, float32 log-softmax",
           "side_cap": L.SIDE_CAP, "texts_sha256": want, "limit": a.limit, "manifest": manifest}
    name_out = "SCORE_SMOKE.json" if a.limit else "SCORE_DONE.json"
    json.dump(rec, open(os.path.join(out, name_out), "w", encoding="utf-8"), indent=1)
    print(f"{a.tier} {name_out} written: {len(units)} units, {done} scored now, {skipped} already present", flush=True)


if __name__ == "__main__":
    main()
