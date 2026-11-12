"""
t0_dev.py — tier 0 development and tuning on the DISJOINT corpus only (D19).

Never reads an evaluation pool. Everything here comes from
data/disjoint_train/documents.jsonl (PMC case reports 2024/01-2025/12, every
evaluation PMCID excluded), split by SHA-256 of the PMCID: 90% train, 10% dev.

  1. Position model: vectorizer fit on train; ridge alpha in {0.3, 1, 3, 10}
     chosen by mean within-document Kendall tau on dev documents.
  2. 46 dev pools of 7 dev documents (5-287 sentences, the evaluation range),
     drawn with seed 42, masked and shuffled exactly as the final runner does.
  3. Grouping: k in {5, 10, 15} x c in {0.5, 1, 2} chosen by mean F1_L over the
     dev pools. Ties go to the first value listed.
  4. Reference only (nothing chosen from it): T0-PUP and the chosen
     T0-classical on the dev pools.

Writes results/final_t0/dev_tuning.json and position_model.pkl (+ SHA-256).

    python runs/t0_dev.py [--max-docs N] [--out DIR]
"""

import argparse
import hashlib
import json
import os
import pickle
import random
import statistics
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
for d in ("adversaries", "harness", "analysis"):
    sys.path.insert(0, os.path.join(ROOT, d))

import numpy as np                                            # noqa: E402
from scipy.stats import kendalltau                           # noqa: E402

import classical_t0 as T0                                     # noqa: E402
from joint_game import _unit_seed, score_row                  # noqa: E402

SEED = 42
ALPHAS = [0.3, 1.0, 3.0, 10.0]
KS = [5, 10, 15]
CS = [0.5, 1.0, 2.0]
N_POOLS, POOL_SIZE, MIN_S, MAX_S = 46, 7, 5, 287


def split_of(pmcid):
    return "dev" if int(hashlib.sha256(pmcid.encode()).hexdigest(), 16) % 10 == 0 else "train"


def load(max_docs):
    docs = []
    for line in open(os.path.join("data", "disjoint_train", "documents.jsonl"), encoding="utf-8"):
        if line.strip():
            docs.append(json.loads(line))
            if max_docs and len(docs) >= max_docs:
                break
    return docs


def make_pools(dev_docs):
    ok = sorted((d for d in dev_docs if MIN_S <= len(d["sentences"]) <= MAX_S), key=lambda d: d["pmcid"])
    rng = random.Random(SEED)
    rng.shuffle(ok)
    need = N_POOLS * POOL_SIZE
    if len(ok) < need:
        raise SystemExit(f"only {len(ok)} eligible dev documents, need {need}")
    pools = []
    for p in range(N_POOLS):
        members = ok[p * POOL_SIZE:(p + 1) * POOL_SIZE]
        frags, truth = [], {}
        for d in members:
            rid = d["pmcid"]
            ids = [f"{rid}_{i:03d}" for i in range(len(d["sentences"]))]
            truth[rid] = ids
            frags += [{"fragment_id": i, "text": s} for i, s in zip(ids, d["sentences"])]
        pools.append((f"dev_{p:02d}", frags, truth))
    return pools


def shown_and_seed(frags):
    shown = [{"fragment_id": f["fragment_id"], "text": f["text"]} for f in frags]
    random.Random(_unit_seed(frags, SEED, "order")).shuffle(shown)
    return shown, _unit_seed(frags, SEED, "labels")


def score(pid, frags, truth, groups):
    key = {r: v for r, v in truth.items()}
    return score_row({"game": "J", "unit": pid, "alias_map": {f["fragment_id"]: f["fragment_id"] for f in frags},
                      "raw_response": groups, "repair": {"policy_share": 0.0}}, key, {pid: truth})


def summarise(rows):
    C, K = sum(r["C"] for r in rows), sum(r["K"] for r in rows)
    return {"F1_J": statistics.fmean(r["joint_f1"] for r in rows),
            "F1_L": statistics.fmean(r["j_linkage_f1"] for r in rows),
            "q_micro": C / K if K else None,
            "base": statistics.fmean(r["joint_baseline"] for r in rows),
            "exact_records": sum(r["exact_records"] for r in rows)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-docs", type=int, default=0)
    ap.add_argument("--out", default=os.path.join("results", "final_t0"))
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    t0 = time.time()

    docs = load(a.max_docs)
    train = [d["sentences"] for d in docs if split_of(d["pmcid"]) == "train"]
    dev = [d for d in docs if split_of(d["pmcid"]) == "dev"]
    print(f"{len(docs)} documents: {len(train)} train, {len(dev)} dev", flush=True)

    # 1. position model
    proto = T0.PositionModel(ALPHAS[0])
    Xtxt, y = proto.targets(train)
    Xtr = proto.vec.fit_transform(Xtxt)
    dev_eval = [d["sentences"] for d in dev if MIN_S <= len(d["sentences"]) <= MAX_S]
    dev_X = [proto.vec.transform(s) for s in dev_eval]
    print(f"vectorizer: {Xtr.shape[0]} sentences, {Xtr.shape[1]} features "
          f"({time.time() - t0:.0f}s)", flush=True)
    alpha_rows, fitted = [], {}
    for alpha in ALPHAS:
        from sklearn.linear_model import Ridge
        reg = Ridge(alpha=alpha, solver="sparse_cg", random_state=0).fit(Xtr, y)
        taus = [kendalltau(reg.predict(X), np.arange(X.shape[0])).statistic for X in dev_X]
        taus = [t for t in taus if not np.isnan(t)]
        alpha_rows.append({"alpha": alpha, "mean_tau": statistics.fmean(taus), "n_docs": len(taus)})
        fitted[alpha] = reg
        print(f"  alpha {alpha:>5}: mean dev tau {alpha_rows[-1]['mean_tau']:.4f}", flush=True)
    best_alpha = max(alpha_rows, key=lambda r: (r["mean_tau"], -ALPHAS.index(r["alpha"])))["alpha"]
    pos = T0.PositionModel(best_alpha)
    pos.vec, pos.reg = proto.vec, fitted[best_alpha]

    # 2. dev pools
    pools = make_pools(dev)
    print(f"{len(pools)} dev pools, {sum(len(p[1]) for p in pools)} fragments", flush=True)

    # 3. grouping grid (F1_L does not depend on the within-group order)
    grid = []
    for k in KS:
        for c in CS:
            rows = []
            for pid, frags, truth in pools:
                shown, ms = shown_and_seed(frags)
                groups, _tel = T0.attack_classical(shown, len(truth), pos, k, c, seed=SEED, mask_seed=ms)
                rows.append(score(pid, frags, truth, groups))
            s = summarise(rows)
            grid.append({"k": k, "c": c, **s})
            print(f"  k {k:>2} c {c:>3}: F1_L {s['F1_L']:.4f}  F1_J {s['F1_J']:.4f}  q {s['q_micro']:.4f}", flush=True)
    best = max(grid, key=lambda r: (r["F1_L"], -KS.index(r["k"]), -CS.index(r["c"])))

    # 4. reference: T0-PUP on the same dev pools
    pup_rows = []
    for pid, frags, truth in pools:
        shown, ms = shown_and_seed(frags)
        groups, _tel = T0.attack_pup(shown, len(truth), seed=SEED, mask_seed=ms)
        pup_rows.append(score(pid, frags, truth, groups))
    pup = summarise(pup_rows)
    print(f"  T0-PUP dev: F1_L {pup['F1_L']:.4f}  F1_J {pup['F1_J']:.4f}  q {pup['q_micro']:.4f}", flush=True)

    mp = os.path.join(a.out, "position_model.pkl")
    with open(mp, "wb") as fh:
        pickle.dump({"vec": pos.vec, "reg": pos.reg, "alpha": best_alpha}, fh)
    out = {"corpus_documents": len(docs), "train_documents": len(train), "dev_documents": len(dev),
           "train_sentences": int(Xtr.shape[0]), "features": int(Xtr.shape[1]),
           "alpha_grid": alpha_rows, "chosen_alpha": best_alpha,
           "grouping_grid": grid, "chosen": {"k": best["k"], "c": best["c"]},
           "dev_T0_classical": {k: best[k] for k in ("F1_J", "F1_L", "q_micro", "base", "exact_records")},
           "dev_T0_PUP": pup, "position_model_sha256": T0.file_sha256(mp),
           "dev_pool_members": {pid: list(truth) for pid, _f, truth in pools},
           "seconds": round(time.time() - t0)}
    json.dump(out, open(os.path.join(a.out, "dev_tuning.json"), "w", encoding="utf-8"), indent=2)
    print(f"chosen: alpha {best_alpha}, k {best['k']}, c {best['c']}; wrote {a.out}", flush=True)


if __name__ == "__main__":
    main()
