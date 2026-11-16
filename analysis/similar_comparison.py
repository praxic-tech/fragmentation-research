"""
similar_comparison.py — POST-HOC EXPLORATORY (RUN_DECISIONS D20): each attacker
on the similar pools against the same attacker on the headline pools. Reads
only; writes results/final_similar/COMPARISON.json and COMPARISON.md.

D20's analysis, as frozen: per attacker F1_J, F1_L, q (micro) and A_J on each
set of 46 pools, and similar - headline with a 95% bootstrap CI (10,000
resamples of pools within each set, seed 42; the two sets hold different
pools, so the resampling is independent, not paired). Reading fixed in D20: a
CI for F1_J entirely below 0 -> similarity helps the defence; otherwise ->
similarity of this kind does not protect.

One descriptive addition that D20 does not contain, labelled as such in the
output: within the similar pools, the Spearman correlation between a pool's
mean within-pool cosine and the attacker's F1_J, and mean F1_J for the most
similar third, the middle third and the least similar third (creation order).
D20 says late pools are leftovers and less similar; this shows whether the
attacker's score follows that.

An attacker with no similar-pool result yet is listed as pending.

    python analysis/similar_comparison.py
"""

import json
import os
import sys

import numpy as np
from scipy.stats import spearmanr

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
for d in ("adversaries", "harness", "analysis", "runs"):
    sys.path.insert(0, os.path.join(ROOT, d))
sys.stdout.reconfigure(encoding="utf-8")

from joint_game import _no_model_answer, build_units, score_row   # noqa: E402

B, SEED = 10_000, 42
OUT = os.path.join("results", "final_similar")
FRAME = os.path.join("data", "pools", "similar_pools.json")
HEAD_SPEC = os.path.join("runs", "final_headlineJ.json")
SON = "One-shot Sonnet"
# attacker: (headline rows, similar rows); Sonnet's are raw model answers, scored here
LOCAL = {"T0-PUP": "final_t0", "T0-classical": "final_t0", "T1-pythia160m": "final_t1",
         "T2-pythia1.4b": "final_t2", "T3-crossenc": "final_t3"}
RAW = {SON: (os.path.join("results", "final", "headlineJ", "prose", "J.jsonl"),
             os.path.join("results", "final", "similarJ", "prose", "J.jsonl"))}
ORDER = [SON, "T3-crossenc", "T2-pythia1.4b", "T0-classical", "T1-pythia160m", "T0-PUP"]


def row(r):
    return {"F1_J": r["joint_f1"], "F1_L": r["j_linkage_f1"], "C": r["C"], "K": r["K"], "b_J": r["joint_baseline"]}


def load_local(path):
    return {r["pool"]: row(r) for r in map(json.loads, open(path, encoding="utf-8"))}


def load_raw(path, pools, cell):
    rb = path.replace("J.jsonl", "J.rbnc.jsonl")
    rbnc = {json.loads(l)["unit"] for l in open(rb, encoding="utf-8") if l.strip()} if os.path.exists(rb) else set()
    members = dict(pools)
    out, unscored = {}, []
    for line in open(path, encoding="utf-8"):
        if not line.strip():
            continue
        r = json.loads(line)
        if r["unit"] in rbnc or _no_model_answer(r):
            unscored.append(r["unit"])
            continue
        pid = r["unit"]
        _o, _u, key, truth = build_units(cell, 0, len(members[pid]), SEED, pools=[(pid, members[pid])], o_docs=[])
        out[pid] = row(score_row(r, key, truth))
    return out, unscored


def stats(rows, idx):
    ids = sorted(rows)
    a = {k: np.array([rows[i][k] for i in ids], dtype=float) for k in ("F1_J", "F1_L", "C", "K", "b_J")}
    aj = (a["F1_J"] - a["b_J"]) / (1 - a["b_J"])
    idx = idx[:, :len(ids)] % len(ids)
    boot = {"F1_J": a["F1_J"][idx].mean(1), "F1_L": a["F1_L"][idx].mean(1), "A_J": aj[idx].mean(1),
            "q": a["C"][idx].sum(1) / a["K"][idx].sum(1)}
    point = {"F1_J": float(a["F1_J"].mean()), "F1_L": float(a["F1_L"].mean()), "A_J": float(aj.mean()),
             "q": float(a["C"].sum() / a["K"].sum())}
    return point, boot, len(ids)


def ci(x):
    return [float(np.percentile(x, 2.5)), float(np.percentile(x, 97.5))]


def main():
    frame = json.load(open(FRAME, encoding="utf-8"))
    sim_pools = [(p["pool_id"], p["members"]) for p in frame["pools"]]
    cosine = {p["pool_id"]: p["mean_within_cosine"] for p in frame["pools"]}
    hb = json.load(open(HEAD_SPEC, encoding="utf-8"))["build"]
    (cell,) = hb["cells"]
    rng = np.random.default_rng(SEED)
    idx_s, idx_h = rng.integers(0, 46, (B, 46)), rng.integers(0, 46, (B, 46))
    res, pending = {}, []
    for att in ORDER:
        if att in RAW:
            hp, sp = RAW[att]
            if not os.path.exists(sp):
                pending.append(att)
                continue
            head, _ = load_raw(hp, hb["pools"], cell)
            sim, unscored = load_raw(sp, sim_pools, cell)
        else:
            hp = os.path.join("results", LOCAL[att], "headlineJ", f"prose.{att}.jsonl")
            sp = os.path.join(OUT, "similarJ", f"prose.{att}.jsonl")
            if not (os.path.exists(hp) and os.path.exists(sp)):
                pending.append(att)
                continue
            head, sim, unscored = load_local(hp), load_local(sp), []
        ps, bs, ns = stats(sim, idx_s)
        ph, bh, nh = stats(head, idx_h)
        e = {"similar": ps | {"pools": ns}, "headline": ph | {"pools": nh}, "similar_unscored": unscored,
             "diff": {k: ps[k] - ph[k] for k in ps}, "diff_ci": {k: ci(bs[k] - bh[k]) for k in ps}}
        e["reading_D20"] = ("similarity helps the defence" if e["diff_ci"]["F1_J"][1] < 0
                            else "similarity of this kind does not protect")
        ids = sorted(sim)
        f = np.array([sim[i]["F1_J"] for i in ids])
        c = np.array([cosine[i] for i in ids])
        rho = spearmanr(c, f)
        thirds = np.array_split(np.arange(len(ids)), 3)          # ids sort in creation order: most similar first
        e["descriptive_not_in_D20"] = {
            "spearman_cosine_vs_F1_J": float(rho.statistic), "spearman_p": float(rho.pvalue),
            "F1_J_by_third": [float(f[t].mean()) for t in thirds],
            "cosine_by_third": [float(c[t].mean()) for t in thirds]}
        res[att] = e
    os.makedirs(OUT, exist_ok=True)
    mc = frame["manipulation_check"]
    json.dump({"decision": "RUN_DECISIONS D20 (post-hoc exploratory)",
               "manipulation_check": {k: v for k, v in mc.items() if k != "headline_per_pool"},
               "pending": pending, "attackers": res},
              open(os.path.join(OUT, "COMPARISON.json"), "w", encoding="utf-8"), indent=1)

    L = ["# Similar pools against headline pools (RUN_DECISIONS D20, post-hoc exploratory)", "",
         f"Mean within-pool cosine: similar {mc['similar_mean']:.3f}, headline {mc['headline_mean']:.3f}. "
         "Same 322 documents and fragments; only pool membership differs. Diff = similar − headline, "
         "95% bootstrap CI (10,000 resamples of pools within each set, seed 42).", "",
         "| Attacker | F1_J similar | F1_J headline | diff F1_J | diff F1_L | diff q | Reading (D20) |",
         "|---|---|---|---|---|---|---|"]
    for att, e in res.items():
        d, c = e["diff"], e["diff_ci"]
        L.append(f"| {att} | {e['similar']['F1_J']:.3f} | {e['headline']['F1_J']:.3f} | "
                 + " | ".join(f"{d[k]:+.3f} [{c[k][0]:+.3f}, {c[k][1]:+.3f}]" for k in ("F1_J", "F1_L", "q"))
                 + f" | {e['reading_D20']} |")
    L += ["", "Descriptive, not in D20: within the similar pools, F1_J for the most similar third, the middle "
          "third and the least similar third, and the Spearman correlation of pool cosine with F1_J.", "",
          "| Attacker | most similar | middle | least similar | Spearman ρ (p) |", "|---|---|---|---|---|"]
    for att, e in res.items():
        x = e["descriptive_not_in_D20"]
        L.append(f"| {att} | " + " | ".join(f"{v:.3f}" for v in x["F1_J_by_third"])
                 + f" | {x['spearman_cosine_vs_F1_J']:+.2f} ({x['spearman_p']:.3g}) |")
    if pending:
        L += ["", "Pending: " + ", ".join(pending) + "."]
    open(os.path.join(OUT, "COMPARISON.md"), "w", encoding="utf-8").write("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
