"""
gate_fix_audit.py — which verdicts does the Game J integrity-gate fix change?

The pre-fix gate read a Game J unit's policy share as 1 - coverage_frac. Game J
rows are scored after the completion policy has filled every missing fragment,
so that is 0 by construction and policy-heavy units passed. The fix
(joint_game.gate_policy_share) takes max(recorded repair.policy_share,
1 - coverage_frac). The new share is never below the old one, so the fix can
only ADD refusals, and only for a unit whose recorded share is over POLICY_CAP.

This scans every raw Game J row under results/ (the sandbox is excluded: it
applied the written rule to the recorded share itself) and lists those units.
For the single-token arm, where the one such unit sits, it also reports the
cell's means with and without that unit.

Writes results/final_analysis/GATE_FIX_AUDIT.json. No API calls.

    python analysis/gate_fix_audit.py
"""

import csv
import glob
import json
import os
import statistics as st
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
sys.path.insert(0, os.path.join(ROOT, "adversaries"))
sys.stdout.reconfigure(encoding="utf-8")

from joint_game import POLICY_CAP, _no_model_answer, _policy_share   # noqa: E402

OUT = os.path.join("results", "final_analysis", "GATE_FIX_AUDIT.json")
PER_POOL = os.path.join("results", "single_token_edge", "analysis", "per_pool.csv")


def scan():
    files, rows, over, shares = [], 0, [], []
    for p in sorted(glob.glob(os.path.join("results", "**", "*.jsonl"), recursive=True)):
        if "cross_model_sandbox" in p:
            continue
        hit = False
        for line in open(p, encoding="utf-8"):
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if not isinstance(r, dict) or r.get("game") != "J" or "raw_response" not in r:
                continue
            hit, rows = True, rows + 1
            if _no_model_answer(r):
                continue
            s = _policy_share(r)
            shares.append(s)
            if s > POLICY_CAP:
                rep = r.get("repair") or {}
                over.append({"file": p.replace(os.sep, "/"), "unit": r.get("unit"),
                             "n_fragments": r.get("n_fragments"), "recorded_policy_share": s,
                             "attempts": [{k: a.get(k) for k in
                                           ("attempt", "n_returned", "n_expected", "n_missing", "valid")}
                                          for a in rep.get("attempts", [])],
                             "forced_finalise": rep.get("forced_finalise")})
        if hit:
            files.append(p.replace(os.sep, "/"))
    below = sorted(s for s in shares if s <= POLICY_CAP)
    return {"raw_j_files": len(files), "raw_j_rows": rows,
            "units_over_cap": over,
            "largest_share_among_the_rest": below[-1] if below else None}


def single_token(units):
    """Sonnet's single-token cell with and without each over-cap unit."""
    pools = {u["unit"] for u in units if "singleTokenEdgeJ/edge__token" in u["file"]}
    if not pools:
        return None
    rows = [r for r in csv.DictReader(open(PER_POOL, encoding="utf-8"))
            if r["attacker"] == "One-shot Sonnet" and r["status"] == "completed"]
    tok = {r["pool"]: r for r in rows if r["condition"] == "token"}
    sen = {r["pool"]: r for r in rows if r["condition"] == "sentence"}
    paired = sorted(set(tok) & set(sen))

    def block(keep):
        m = lambda c, k: st.fmean(float(c[p][k]) for p in keep)
        d = [float(sen[p]["A_VJ"]) - float(tok[p]["A_VJ"]) for p in keep]
        return {"pools": len(keep),
                "token_F1_J": m(tok, "F1_J"), "token_F1_L": m(tok, "F1_L"),
                "token_A_VJ": m(tok, "A_VJ"), "sentence_A_VJ": m(sen, "A_VJ"),
                "paired_A_VJ_sentence_minus_token": st.fmean(d),
                "pools_sentence_higher": sum(x > 0 for x in d)}

    return {"refused_cell": "singleTokenEdgeJ / edge__token (one-shot Sonnet)",
            "over_cap_pools": sorted(pools),
            "all_pools": block(paired),
            "without_over_cap_pools": block([p for p in paired if p not in pools])}


def main():
    res = {"rule": f"a unit is policy-heavy if its recorded policy share exceeds {POLICY_CAP}",
           "why_only_these_can_change": "the fixed share is max(recorded, 1 - coverage) >= the old share",
           **scan()}
    res["single_token_sensitivity"] = single_token(res["units_over_cap"])
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(res, open(OUT, "w", encoding="utf-8"), indent=2)
    print(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
