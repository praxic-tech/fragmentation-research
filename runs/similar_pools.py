"""
similar_pools.py — the similar-pools frame (RUN_DECISIONS D20, POST-HOC
EXPLORATORY). The 322 headline documents regrouped into 46 pools of 7 by
content similarity; nothing is requested or scored here.

Similarity: TF-IDF over each document's full text (sentences joined with
spaces, from the headline fragment file data/prose), fitted on the 322
documents (lower-cased word tokens, English stop words, min_df 2, sublinear
tf, smoothed idf, L2), cosine.
Rule: repeatedly take the unused document whose candidate pool (itself + its 6
most similar unused documents) has the highest mean pairwise cosine; ties to
the lower document id.

Writes data/pools/similar_pools.json (refuses to overwrite) with the
manipulation check: mean within-pool cosine for every similar and every
headline pool.

    python runs/similar_pools.py
"""

import itertools
import json
import os
import statistics
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
for d in ("adversaries", "harness"):
    sys.path.insert(0, os.path.join(ROOT, d))

import numpy as np                                             # noqa: E402
from sklearn.feature_extraction.text import TfidfVectorizer    # noqa: E402

from batch_game import headline_docs, load_frame               # noqa: E402

OUT = os.path.join("data", "pools", "similar_pools.json")
POOL, N_POOLS = 7, 46


def mean_pair(C, idx):
    return float(np.mean([C[a, b] for a, b in itertools.combinations(idx, 2)]))


def main():
    if os.path.exists(OUT):
        raise SystemExit(f"{OUT} exists: the frame is built once.")
    docs = sorted(headline_docs())
    assert len(docs) == POOL * N_POOLS, len(docs)
    text = {d: [] for d in docs}
    for line in open(os.path.join("data", "prose", "prose_fragments.jsonl"), encoding="utf-8"):
        f = json.loads(line)
        if f["record_id"] in text:
            text[f["record_id"]].append((f["fragment_id"], f["text"]))
    full = [" ".join(t for _i, t in sorted(text[d])) for d in docs]
    X = TfidfVectorizer(lowercase=True, stop_words="english", min_df=2, sublinear_tf=True,
                        smooth_idf=True, norm="l2").fit_transform(full)
    C = (X @ X.T).toarray()
    np.fill_diagonal(C, -np.inf)

    unused = list(range(len(docs)))                       # indices into sorted docs: lower index = lower id
    pools = []
    while unused:
        best = None
        for d in unused:
            others = [o for o in unused if o != d]
            nn = sorted(others, key=lambda o: (-C[d, o], o))[:POOL - 1]
            cand = sorted([d] + nn)
            s = mean_pair(C, cand)
            if best is None or s > best[0]:               # strict: ties keep the lower seed id
                best = (s, d, cand)
        s, d, cand = best
        pools.append({"pool_id": f"sim_{len(pools) + 1:03d}", "members": [docs[i] for i in cand],
                      "seed_doc": docs[d], "mean_within_cosine": s})
        unused = [u for u in unused if u not in cand]
    assert len(pools) == N_POOLS

    pos = {d: i for i, d in enumerate(docs)}
    grid_ids = os.path.join("data", "pools", "linkage_grid.json")
    grid = {pid for pid, _m in load_frame(os.path.join("data", "pools", "pools.json"), grid_ids)}
    head = [(pid, m) for pid, m in load_frame(os.path.join("data", "pools", "pools.json")) if pid not in grid]
    assert len(head) == N_POOLS
    head_sims = {pid: mean_pair(C, [pos[x] for x in m]) for pid, m in head}
    sim_sims = [p["mean_within_cosine"] for p in pools]
    check = {"similar_mean": statistics.fmean(sim_sims), "similar_median": statistics.median(sim_sims),
             "similar_min": min(sim_sims), "similar_max": max(sim_sims),
             "headline_mean": statistics.fmean(head_sims.values()),
             "headline_median": statistics.median(head_sims.values()),
             "headline_min": min(head_sims.values()), "headline_max": max(head_sims.values()),
             "all_pairs_mean": float(C[np.triu_indices(len(docs), 1)].mean()),
             "similar_pools_above_headline_max": sum(s > max(head_sims.values()) for s in sim_sims),
             "headline_per_pool": head_sims}
    json.dump({"decision": "RUN_DECISIONS D20 (post-hoc exploratory)", "pool_size": POOL, "n_pools": N_POOLS,
               "documents": "the 322 headline documents (batch_game.headline_docs)",
               "similarity": "TF-IDF (english stop words, min_df 2, sublinear tf, smooth idf, l2) cosine "
                             "over the full document text, fitted on the 322 documents",
               "pools": pools, "manipulation_check": check}, open(OUT, "w", encoding="utf-8"), indent=1)
    print(json.dumps({k: (round(v, 4) if isinstance(v, float) else v) for k, v in check.items()
                      if k != "headline_per_pool"}, indent=1))
    print("first / last pools:", [(p["pool_id"], round(p["mean_within_cosine"], 3)) for p in pools[:3] + pools[-3:]])


if __name__ == "__main__":
    main()
