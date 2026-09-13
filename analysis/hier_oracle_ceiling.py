"""
hier_oracle_ceiling.py — GO / NO-GO for the paid hierarchical run. Free: no API.

A DIAGNOSTIC, NEVER AN ATTACKER RESULT. The hierarchical attacker only ever asks
Sonnet about the pairs its blocker exposes. This keeps the frozen blocker
(k = 20, D8), the candidate graph, bridge rounds, clustering and ordering exactly
as in the run, and replaces Sonnet's pair judgements with the ANSWER KEY on
those exposed pairs only. What it scores is the best the architecture could do
with a perfect pair classifier: its CEILING.

Development data only; 0 headline documents are read:
  headline analogue  data/prose (semantic x sentence, FULL length) on the 25
                     development pools -- the shape the paid run faces
  grid cells         the four cells where one-shot J is projected to exhaust
                     128k, and semantic x sentence for comparison, 25 pools each

THE RULE, FIXED BEFORE ANY NUMBER IS SEEN (median oracle F1_J, headline analogue)
  >= 0.80   HIGH: the blocker leaves enough; the real attacker is worth keeping
  <  0.60   LOW: blocker-limited; a low real score says little about the defence
            -> drop the paid headline run, or keep only as a secondary
               resource-completion experiment
  between   KEEP ONLY AS SECONDARY

    python analysis/hier_oracle_ceiling.py
"""

import json
import os
import statistics as st
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
os.chdir(ROOT)
for d in ("adversaries", "harness", "analysis"):
    sys.path.insert(0, os.path.join(ROOT, d))

from batch_game import headline_docs, load_frame                  # noqa: E402
from hier_batch import DEFAULT_K                                  # noqa: E402
from hierarchical import attack, score_pairs_offline, top_k_candidates  # noqa: E402
from joint_game import build_units, present, score_row            # noqa: E402

K = DEFAULT_K
SEED = 42
CAL = json.load(open("results/audit/hier_blocker_calibration.json", encoding="utf-8"))
USD_PER_PAIR = (CAL["cost_basis"]["in_tok_per_pair"] / 1e6 * 1.0
                + CAL["cost_basis"]["out_tok_per_pair"] / 1e6 * 5.0)
DATASETS = [("headline analogue (full length)", "data/prose"),
            ("semantic x sentence (grid)", "results/grid_A/semantic__sentence"),
            ("random x token-window (grid)", "results/grid_A/random__token-window"),
            ("coherence-sever x token-window (grid)", "results/grid_A/coherence-sever__token-window"),
            ("subject-verb x sentence (grid)", "results/grid_A/subject-verb__sentence"),
            ("subject-verb x clause (grid)", "results/grid_A/subject-verb__clause")]
HIGH, LOW = 0.80, 0.60


def components(nodes, edges):
    parent = {v: v for v in nodes}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    for a, b in edges:
        parent[find(a)] = find(b)
    return len({find(v) for v in nodes})


def run_pool(cell_dir, pid, members):
    _o, units, key, truth = build_units(cell_dir, 0, 7, SEED, pools=[(pid, members)], o_docs=[])
    items, id_map, _shown = present(units[0][1], SEED)
    masked = [{"fragment_id": lab, "text": t} for lab, t in items]
    text = dict(items)
    where = {fid: (rid, i) for rid, order in truth[pid].items() for i, fid in enumerate(order)}
    loc = {lab: where[id_map[lab]] for lab in id_map}
    labels = list(id_map)

    def oracle(i, j):
        (ri, pi), (rj, pj) = loc[i], loc[j]
        return (1.0, 1.0 if pi < pj else 0.0) if ri == rj else (0.0, 0.5)

    cand, _info = top_k_candidates(labels, text, k=K)
    cset = set(cand)
    same = {(a, b) for a in labels for b in labels if a < b and loc[a][0] == loc[b][0]}
    adj = {(a, b) for (a, b) in same if abs(loc[a][1] - loc[b][1]) == 1}
    recs = defaultdict(list)
    for lab in labels:
        recs[loc[lab][0]].append(lab)
    within = [e for e in cset if e in same]
    connected = sum(components(fr, [e for e in within if e[0] in fr and e[1] in fr]) == 1
                    for fr in recs.values())

    groups, tel = attack(masked, len(members),
                         lambda pairs: score_pairs_offline(pairs, oracle, seed=SEED), k=K, seed=SEED)
    s = score_row({"game": "J", "unit": pid, "alias_map": id_map, "raw_response": groups,
                   "repair": {"policy_share": 0.0}}, key, truth)
    return {"n_fragments": len(labels), "same": len(same), "same_hit": len(cset & same),
            "adj": len(adj), "adj_hit": len(cset & adj), "records": len(recs),
            "records_connected": connected, "pairs_asked": tel["scored_edges"],
            "bridge_rounds": tel["bridge_rounds"],
            "evidence_free_merges": tel["clustering"].get("evidence_free_merges", 0),
            "oracle_joint_f1": s["joint_f1"], "oracle_linkage_f1": s["f1"], "oracle_q": s["q"],
            "oracle_joint_advantage": s["joint_advantage"]}


def main():
    print(__doc__.split("THE RULE, FIXED BEFORE ANY NUMBER IS SEEN")[1].split("python ")[0].rstrip())
    frame = load_frame("data/pools/pools.json", "data/pools/linkage_grid.json")
    assert not ({m for _p, ms in frame for m in ms} & headline_docs())
    out = {"what": "oracle CEILING of the hierarchical architecture -- a diagnostic, never an attacker result",
           "k": K, "rule": {"high": HIGH, "low": LOW}, "datasets": {}}
    print(f"\n{'dataset (25 dev pools each)':<40}{'frags':>6}{'same rec':>9}{'adjacent':>9}{'records':>9}"
          f"{'oracle':>8}{'oracle':>8}{'oracle':>8}{'  pairs':>8}{'   $':>7}")
    print(f"{'':<40}{'/pool':>6}{'recall':>9}{'recall':>9}{'conn.':>9}{'F1_L':>8}{'q':>8}{'F1_J':>8}{'/pool':>8}{'/pool':>7}")
    for name, cell_dir in DATASETS:
        rows = [run_pool(cell_dir, pid, members) for pid, members in frame]
        agg = lambda k: sum(r[k] for r in rows)
        d = {"pools": rows,
             "fragments_per_pool": agg("n_fragments") / len(rows),
             "same_record_recall": agg("same_hit") / agg("same"),
             "adjacent_recall": agg("adj_hit") / agg("adj"),
             "records_connected": agg("records_connected") / agg("records"),
             "oracle_linkage_f1_median": st.median(r["oracle_linkage_f1"] for r in rows),
             "oracle_q_median": st.median(r["oracle_q"] for r in rows if r["oracle_q"] is not None),
             "oracle_joint_f1_median": st.median(r["oracle_joint_f1"] for r in rows),
             "oracle_joint_f1_min": min(r["oracle_joint_f1"] for r in rows),
             "pairs_per_pool": agg("pairs_asked") / len(rows),
             "usd_per_pool": agg("pairs_asked") / len(rows) * USD_PER_PAIR}
        big = [r for r in rows if r["n_fragments"] >= 330]
        if big:
            d["large_pools_330plus"] = {"n": len(big),
                                        "oracle_joint_f1_median": st.median(r["oracle_joint_f1"] for r in big),
                                        "usd_per_pool": st.mean(r["pairs_asked"] for r in big) * USD_PER_PAIR}
        out["datasets"][name] = d
        print(f"{name:<40}{d['fragments_per_pool']:>6.0f}{d['same_record_recall']:>9.1%}{d['adjacent_recall']:>9.1%}"
              f"{d['records_connected']:>9.1%}{d['oracle_linkage_f1_median']:>8.3f}{d['oracle_q_median']:>8.3f}"
              f"{d['oracle_joint_f1_median']:>8.3f}{d['pairs_per_pool']:>8.0f}{d['usd_per_pool']:>7.2f}", flush=True)
    h = out["datasets"][DATASETS[0][0]]["oracle_joint_f1_median"]
    verdict = "HIGH -> KEEP" if h >= HIGH else ("LOW -> DROP or KEEP ONLY AS SECONDARY" if h < LOW
                                                else "BETWEEN -> KEEP ONLY AS SECONDARY")
    out["verdict_headline_analogue"] = {"median_oracle_joint_f1": h, "verdict": verdict}
    print(f"\nRULE on the headline analogue: median oracle F1_J {h:.3f} -> {verdict}")
    os.makedirs("results/audit", exist_ok=True)
    with open("results/audit/hier_oracle_ceiling.json", "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1)
    print("wrote results/audit/hier_oracle_ceiling.json  (diagnostic only; never an attacker result)")


if __name__ == "__main__":
    main()
