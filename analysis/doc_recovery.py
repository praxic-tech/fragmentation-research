"""
doc_recovery.py — POST-HOC DIAGNOSTIC (RUN_DECISIONS D21): what an attacker
holds for each headline document. Reads stored answers only; no model calls.

For each true document: its best group is the answer group holding the most of
its fragments (ties: the smaller group, then the first). Completeness = share
of the document's fragments in that group; purity = share of that group that
is the document's. Reported per attacker over the 46 headline pools: mean
completeness, mean purity, and the share of documents with both at least
0.5 / 0.8 / 0.9. Pools are the unit (95% percentile bootstrap, 10,000
resamples, seed 42). Size-blind random reference: 200 seeded round-robin deals
per pool.

Writes results/final_analysis/DOC_RECOVERY.json.

    python analysis/doc_recovery.py
"""

import json
import os
import random
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
for d in ("adversaries", "harness", "analysis"):
    sys.path.insert(0, os.path.join(ROOT, d))
sys.stdout.reconfigure(encoding="utf-8")

from joint_game import _as_groups, _no_model_answer, build_units   # noqa: E402

B, SEED, DRAWS = 10_000, 42, 200
THRESHOLDS = (0.5, 0.8, 0.9)
SPEC = os.path.join("runs", "final_headlineJ.json")
SB = os.path.join("experiments", "cross_model_sandbox", "results")
OUT = os.path.join("results", "final_analysis", "DOC_RECOVERY.json")
LOCAL = [("Memon-inspired", os.path.join("results", "final_free", "headlineJ", "prose.memon_joint.jsonl")),
         ("Embedding (post-hoc exploratory)",
          os.path.join("results", "final_embedding", "headlineJ", "prose.embedding_joint.jsonl")),
         ("T0-PUP", os.path.join("results", "final_t0", "headlineJ", "prose.T0-PUP.jsonl")),
         ("T0-classical", os.path.join("results", "final_t0", "headlineJ", "prose.T0-classical.jsonl")),
         ("T1-pythia160m", os.path.join("results", "final_t1", "headlineJ", "prose.T1-pythia160m.jsonl")),
         ("T2-pythia1.4b", os.path.join("results", "final_t2", "headlineJ", "prose.T2-pythia1.4b.jsonl")),
         ("T3-crossenc", os.path.join("results", "final_t3", "headlineJ", "prose.T3-crossenc.jsonl"))]
RAW = [("One-shot Sonnet", os.path.join("results", "final", "headlineJ", "prose", "J.jsonl"), None),
       ("gpt-5.6-sol (post hoc)", os.path.join(SB, "gpt-5.6-sol", "final_headlineJ", "prose", "J.jsonl"), 1),
       ("deepseek-v3.2 (post hoc)", os.path.join(SB, "deepseek-v3.2", "final_headlineJ", "prose", "J.jsonl"), 1)]


def pad(groups, all_ids):
    """The scorer's reading: unknown labels dropped, unplaced fragments are singletons."""
    groups = [[f for f in g if f in all_ids] for g in groups]
    groups = [g for g in groups if g]
    placed = {f for g in groups for f in g}
    return groups + [[f] for f in sorted(all_ids - placed)]


def per_doc(groups, tg):
    """[(completeness, purity)] for each true document."""
    out = []
    sets = [set(g) for g in groups]
    for _rid, frags in sorted(tg.items()):
        F = set(frags)
        best = max(range(len(sets)), key=lambda i: (len(sets[i] & F), -len(sets[i]), -i))
        hit = len(sets[best] & F)
        out.append((hit / len(F), hit / len(sets[best])))
    return out


def pool_stats(docs):
    c = np.array([d[0] for d in docs])
    p = np.array([d[1] for d in docs])
    s = {"completeness": float(c.mean()), "purity": float(p.mean())}
    for t in THRESHOLDS:
        s[f"both_ge_{t}"] = float(((c >= t) & (p >= t)).mean())
    return s


def summarise(per_pool, idx):
    keys = list(next(iter(per_pool.values())))
    pools = sorted(per_pool)
    out = {"pools": len(pools)}
    for k in keys:
        a = np.array([per_pool[p][k] for p in pools])
        boot = a[idx[:, :len(pools)] % len(pools)].mean(1) if len(pools) != idx.shape[1] else a[idx].mean(1)
        out[k] = float(a.mean())
        out[k + "_ci"] = [float(np.percentile(boot, 2.5)), float(np.percentile(boot, 97.5))]
    return out


def main():
    b = json.load(open(SPEC, encoding="utf-8"))["build"]
    (cell_dir,) = b["cells"]
    truth = {}
    for pid, members in b["pools"]:
        _o, _u, _key, tr = build_units(cell_dir, 0, len(members), SEED, pools=[(pid, members)], o_docs=[])
        truth[pid] = tr[pid]
    pools = sorted(truth)
    assert len(pools) == 46 and sum(len(t) for t in truth.values()) == 322
    idx = np.random.default_rng(SEED).integers(0, 46, (B, 46))
    res, not_run = {}, []

    def add(name, answers):
        per_pool = {}
        for pid, groups in answers.items():
            all_ids = {f for v in truth[pid].values() for f in v}
            per_pool[pid] = pool_stats(per_doc(pad(groups, all_ids), truth[pid]))
        res[name] = summarise(per_pool, idx)

    for name, path, sweep in RAW:
        ans = {}
        rb = path.replace("J.jsonl", "J.rbnc.jsonl")
        rbnc = {json.loads(l)["unit"] for l in open(rb, encoding="utf-8") if l.strip()} \
            if os.path.exists(rb) else set()
        for line in open(path, encoding="utf-8"):
            if not line.strip():
                continue
            r = json.loads(line)
            if r["unit"] in rbnc or (sweep and _no_model_answer(r)):
                continue
            g = _as_groups(r["raw_response"])
            ans[r["unit"]] = [[r["alias_map"][l] for l in grp if l in r["alias_map"]] for grp in g]
        add(name, ans)
    for name, path in LOCAL:
        if not os.path.exists(path):
            not_run.append(name)
            continue
        add(name, {r["pool"]: r["reconstruction"] for r in map(json.loads, open(path, encoding="utf-8"))})

    per_pool = {}
    for pid in pools:
        ids = sorted(f for v in truth[pid].values() for f in v)
        n = len(truth[pid])
        acc = []
        for d in range(DRAWS):
            rng = random.Random(f"{SEED}:{pid}:{d}")
            sh = ids[:]
            rng.shuffle(sh)
            acc.append(pool_stats(per_doc([sh[i::n] for i in range(n)], truth[pid])))
        per_pool[pid] = {k: float(np.mean([a[k] for a in acc])) for k in acc[0]}
    res["Random valid N-group (size-blind)"] = summarise(per_pool, idx)

    json.dump({"decision": "RUN_DECISIONS D21 (post-hoc diagnostic)", "documents": 322, "thresholds": THRESHOLDS,
               "not_run": not_run, "attackers": res}, open(OUT, "w", encoding="utf-8"), indent=1)
    print(f"{'attacker':36s} pools  complete  purity   >=0.5   >=0.8   >=0.9")
    for name, s in res.items():
        print(f"{name:36s} {s['pools']:5d}  {s['completeness']:.3f}     {s['purity']:.3f}   "
              + "   ".join(f"{s[f'both_ge_{t}']:.3f}" for t in THRESHOLDS))
    if not_run:
        print("not run:", ", ".join(not_run))


if __name__ == "__main__":
    main()
