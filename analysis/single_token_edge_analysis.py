"""
single_token_edge_analysis.py — the frozen analysis of the POST-HOC EXPLORATORY —
CONTROLLED SINGLE-TOKEN EDGE-CASE EXPERIMENT (RUN_DECISIONS D16;
docs/single_token_edge_design.md). Written, self-tested on synthetic answers and
committed BEFORE any Sonnet result of this experiment was read.

Primary (exploratory): the paired A_VJ(sentence) - A_VJ(token) for one-shot Sonnet,
    A_VJ = (V_J - mean oracle-size null V_J) / (1 - mean oracle-size null V_J),
over pools where BOTH conditions completed (n_effective). Paired percentile
bootstrap (10,000 resamples of the pool, seed 42, 95%) and the exact two-sided
sign test (zero differences are ties, omitted). Secondary: raw V_J, raw V_L,
A_VL, id-level F1_J, F1_L, A_J, and the predicted-structure-null sensitivity.
If raw and normalised paired differences disagree in sign for any pool, every
such pool is reported. RBNC is never scored; completion is reported separately.
Memon-inspired and MPNet are reported but are NOT security evidence at the token
level (neither was designed for isolated tokens).

    python analysis/single_token_edge_analysis.py              # the frozen analysis
    python analysis/single_token_edge_analysis.py --selftest   # synthetic answers, 200 draws, temp dir
"""

import argparse
import csv
import glob
import json
import os
import random
import shutil
import statistics as st
import sys
import tempfile
from concurrent.futures import ProcessPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
for d in ("adversaries", "harness", "analysis"):
    sys.path.insert(0, os.path.join(ROOT, d))

import numpy as np                                                        # noqa: E402
from scipy.stats import binomtest                                         # noqa: E402

from batch_game import at_ceiling                                         # noqa: E402
from joint_game import _as_groups, build_units, score_row                 # noqa: E402
from visible_metrics import (PoolScorer, advantage, null_rng,             # noqa: E402
                             oracle_size_null, predicted_structure_null)

FROZEN = json.load(open("results/single_token_edge/FROZEN_DESIGN.json", encoding="utf-8"))
POOLS = [(p["pool_id"], p["members"]) for p in json.load(open(FROZEN["pools_file"], encoding="utf-8"))["pools"]]
CELLS = {"sentence": FROZEN["cells"][0], "token": FROZEN["cells"][1]}
N_PERM = FROZEN["permutations_per_pool_condition_null"]
B, SEED = 10_000, 42
SON, MEM, EMB = "One-shot Sonnet", "Memon-inspired", "Embedding (post-hoc exploratory)"
LOCAL_FILE = {MEM: "memon-inspired", EMB: "embedding"}
LABEL = "POST-HOC EXPLORATORY — CONTROLLED SINGLE-TOKEN EDGE-CASE EXPERIMENT"

_PS = {}


def scorer(cond, pid, members):
    if (cond, pid) not in _PS:
        _o, units, key, truth = build_units(CELLS[cond], 0, 7, SEED, pools=[(pid, members)], o_docs=[])
        _PS[(cond, pid)] = (PoolScorer(truth[pid], {f["fragment_id"]: f["text"] for f in units[0][1]}), key, truth)
    return _PS[(cond, pid)]


def null_task(args):
    kind, attacker, cond, pid, members, groups, n_perm = args
    ps, _k, _t = scorer(cond, pid, members)
    rng = null_rng(pid, cond, kind)
    arr = oracle_size_null(ps, n_perm, rng) if kind == "oracle-size" else predicted_structure_null(ps, groups, n_perm, rng)
    m = arr.mean(0)
    return kind, attacker, cond, pid, float(m[0]), float(m[1])


def load_sonnet(res_root, cond):
    d = os.path.join(res_root, "singleTokenEdgeJ", os.path.basename(CELLS[cond]))
    rows, rb = {}, set()
    if os.path.exists(os.path.join(d, "J.jsonl")):
        rows = {json.loads(l)["unit"]: json.loads(l) for l in open(os.path.join(d, "J.jsonl"), encoding="utf-8") if l.strip()}
    if os.path.exists(os.path.join(d, "J.rbnc.jsonl")):
        rb = {json.loads(l)["unit"] for l in open(os.path.join(d, "J.rbnc.jsonl"), encoding="utf-8") if l.strip()}
    return rows, rb


def paired(a, b):
    """a, b: pool -> value. Resample the pool once, carrying both conditions."""
    pools = [p for p in a if p in b and a[p] is not None and b[p] is not None]
    if not pools:
        return {"n_effective": 0}
    d = np.array([a[p] - b[p] for p in pools])
    i = np.random.default_rng(SEED).integers(0, len(d), size=(B, len(d)))
    bs, bm = d[i].mean(1), np.median(d[i], axis=1)
    nz = d[d != 0]
    pos = int((nz > 0).sum())
    return {"n_effective": len(d), "n_nonzero": int(len(nz)), "n_positive": pos,
            "mean_diff": float(d.mean()), "ci95": [float(np.quantile(bs, .025)), float(np.quantile(bs, .975))],
            "median_diff": float(np.median(d)), "median_ci95": [float(np.quantile(bm, .025)), float(np.quantile(bm, .975))],
            "sign_test_p_two_sided": float(binomtest(pos, len(nz), 0.5).pvalue) if len(nz) else None,
            "per_pool": {p: float(a[p] - b[p]) for p in pools}}


def resources(batch_glob):
    out = {c: {"requests_rows": 0, "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0, "at_128k": 0,
               "refused_for_credit": 0} for c in CELLS}
    for p in glob.glob(batch_glob):
        for l in open(p, encoding="utf-8"):
            if not l.strip():
                continue
            r = json.loads(l)
            c = "sentence" if r["custom_id"].startswith("edge-sentence") else "token"
            u = r.get("usage") or {}
            o = out[c]
            o["requests_rows"] += 1
            o["input_tokens"] += u.get("input_tokens", 0) or 0
            o["output_tokens"] += u.get("output_tokens", 0) or 0
            o["cost_usd"] += (u.get("input_tokens", 0) or 0) / 1e6 + (u.get("output_tokens", 0) or 0) * 5 / 1e6
            o["at_128k"] += bool(at_ceiling(r))
            o["refused_for_credit"] += "credit balance" in str(r.get("error"))
    return out


def run(res_root, local_root, batch_glob, out_dir, n_perm, workers=6):
    os.makedirs(out_dir, exist_ok=True)
    recon, status, ordinary = {}, {}, {}
    for cond in CELLS:
        rows, rb = load_sonnet(res_root, cond)
        for pid, members in POOLS:
            ps, key, truth = scorer(cond, pid, members)
            if pid in rows:
                r = rows[pid]
                al = r["alias_map"]
                g = [[al[x] for x in grp if x in al] for grp in _as_groups(r["raw_response"])]
                recon[(SON, cond, pid)] = [x for x in g if x]
                sc = score_row(r, key, truth)
                ordinary[(SON, cond, pid)] = {"F1_J": sc["joint_f1"], "F1_L": sc["j_linkage_f1"], "q": sc["q"],
                                             "b_J": sc["joint_baseline"], "A_J": sc["joint_advantage"]}
                status[(SON, cond, pid)] = "completed"
            else:
                status[(SON, cond, pid)] = "rbnc" if pid in rb else "missing"
        for att, stem in LOCAL_FILE.items():
            p = os.path.join(local_root, f"{stem}__{os.path.basename(CELLS[cond])}.jsonl")
            loc = {json.loads(l)["pool"]: json.loads(l) for l in open(p, encoding="utf-8") if l.strip()} if os.path.exists(p) else {}
            for pid, _m in POOLS:
                if pid in loc:
                    recon[(att, cond, pid)] = loc[pid]["reconstruction"]
                    ordinary[(att, cond, pid)] = {k: loc[pid][k] for k in ("F1_J", "F1_L", "q", "b_J", "A_J")}
                    status[(att, cond, pid)] = "completed"
                else:
                    status[(att, cond, pid)] = "missing"
    tasks = [("oracle-size", None, cond, pid, m, None, n_perm) for cond in CELLS for pid, m in POOLS]
    tasks += [("predicted-structure", att, cond, pid, m, recon[(att, cond, pid)], n_perm)
              for (att, cond, pid) in recon for p2, m in POOLS if p2 == pid]
    nulls = {}
    with ProcessPoolExecutor(max_workers=workers) as ex:
        for kind, att, cond, pid, ml, mj in ex.map(null_task, tasks, chunksize=1):
            nulls[(kind, att, cond, pid)] = (ml, mj)
    rows = []
    for (att, cond, pid), st_ in sorted(status.items()):
        row = {"attacker": att, "condition": cond, "pool": pid, "status": st_,
               "n_fragments": len(scorer(cond, pid, dict(POOLS)[pid])[0].all_ids)}
        if st_ == "completed":
            ps = scorer(cond, pid, dict(POOLS)[pid])[0]
            v = ps.score(recon[(att, cond, pid)])
            o_l, o_j = nulls[("oracle-size", None, cond, pid)]
            p_l, p_j = nulls[("predicted-structure", att, cond, pid)]
            row.update({"V_L": v["V_L"], "V_J": v["V_J"], "q_V": v["q_V"],
                        "null_oracle_V_L": o_l, "null_oracle_V_J": o_j, "A_VL": advantage(v["V_L"], o_l),
                        "A_VJ": advantage(v["V_J"], o_j), "null_pred_V_L": p_l, "null_pred_V_J": p_j,
                        "A_VL_pred": advantage(v["V_L"], p_l), "A_VJ_pred": advantage(v["V_J"], p_j),
                        **ordinary[(att, cond, pid)]})
            assert v["V_J"] <= v["V_L"] + 1e-12
        rows.append(row)
    cols = []
    for r in rows:
        cols += [k for k in r if k not in cols]
    with open(os.path.join(out_dir, "per_pool.csv"), "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow({k: ("" if r.get(k) is None else r.get(k)) for k in cols})

    def vals(att, cond, k):
        return {r["pool"]: r.get(k) for r in rows if r["attacker"] == att and r["condition"] == cond and r["status"] == "completed"}

    summary = {"label": LABEL, "n_selected": len(POOLS), "permutations": n_perm, "attackers": {}}
    for att in (SON, MEM, EMB):
        comp = {c: sum(1 for r in rows if r["attacker"] == att and r["condition"] == c and r["status"] == "completed")
                for c in CELLS}
        rbnc = {c: sorted(r["pool"] for r in rows if r["attacker"] == att and r["condition"] == c and r["status"] == "rbnc")
                for c in CELLS}
        means = {c: {k: (st.fmean(v for v in vals(att, c, k).values() if v is not None)
                         if any(v is not None for v in vals(att, c, k).values()) else None)
                     for k in ("V_J", "V_L", "A_VJ", "A_VL", "A_VJ_pred", "F1_J", "F1_L", "A_J", "q_V")} for c in CELLS}
        pr = {k: paired(vals(att, "sentence", k), vals(att, "token", k))
              for k in ("A_VJ", "V_J", "V_L", "A_VL", "A_VJ_pred", "F1_J", "F1_L", "A_J")}
        dis = sorted(p for p in pr["A_VJ"].get("per_pool", {})
                     if p in pr["V_J"].get("per_pool", {}) and pr["V_J"]["per_pool"][p] != 0 and pr["A_VJ"]["per_pool"][p] != 0
                     and (pr["V_J"]["per_pool"][p] > 0) != (pr["A_VJ"]["per_pool"][p] > 0))
        summary["attackers"][att] = {"n_complete": comp, "rbnc": rbnc,
                                     "n_effective": pr["A_VJ"].get("n_effective", 0),
                                     "n_nonzero": pr["A_VJ"].get("n_nonzero", 0), "means": means,
                                     "paired_sentence_minus_token": {k: {kk: vv for kk, vv in v.items() if kk != "per_pool"}
                                                                     for k, v in pr.items()},
                                     "raw_vs_normalised_sign_disagreement_pools": dis}
    summary["resources"] = resources(batch_glob)
    hb = "results/final_analysis/TABLES/table_B_headline_J.csv"
    if os.path.exists(hb):
        h = next(r for r in csv.DictReader(open(hb, encoding="utf-8")) if r["attacker"] == SON)
        summary["descriptive_excerpt_vs_headline_F1_J"] = {
            "excerpt_sentence_arm_F1_J_mean": summary["attackers"][SON]["means"]["sentence"]["F1_J"],
            "headline_full_document_F1_J_mean": float(h["F1_J_mean"]),
            "note": "common metric only (F1_J); descriptive; cannot alter the experiment"}
    json.dump(summary, open(os.path.join(out_dir, "summary.json"), "w", encoding="utf-8"), indent=2)
    write_md(summary, out_dir)
    return summary


def write_md(S, out_dir):
    f = lambda v, d=3: "—" if v is None else f"{v:.{d}f}"
    L = [f"# {LABEL}: results", "",
         "RUN_DECISIONS D16. **Post-hoc exploratory; not prespecified or confirmatory.** Frozen analysis "
         "(analysis/single_token_edge_analysis.py, committed before any result was read).", "",
         f"n_selected {S['n_selected']} pools; {S['permutations']:,} permutation draws per pool × condition × null.", ""]
    for att, a in S["attackers"].items():
        pr = a["paired_sentence_minus_token"]
        L += [f"## {att}", "",
              f"- completion: sentence {a['n_complete']['sentence']}/{S['n_selected']}, token "
              f"{a['n_complete']['token']}/{S['n_selected']}; RBNC: sentence {a['rbnc']['sentence'] or 'none'}, token "
              f"{a['rbnc']['token'] or 'none'}",
              f"- n_effective (both conditions completed) {a['n_effective']}; n_nonzero {a['n_nonzero']}", "",
              "| metric | sentence mean | token mean | paired mean diff (s − t) [95% CI] | median diff | sign test p (two-sided) |",
              "|---|---|---|---|---|---|"]
        for k in ("A_VJ", "V_J", "V_L", "A_VL", "A_VJ_pred", "F1_J", "F1_L", "A_J"):
            p = pr[k]
            if not p.get("n_effective"):
                L.append(f"| {k} | {f(a['means']['sentence'][k])} | {f(a['means']['token'][k])} | no completed pairs | — | — |")
                continue
            L.append(f"| {k}{' (PRIMARY)' if k == 'A_VJ' and att == SON else ''} | {f(a['means']['sentence'][k])} | "
                     f"{f(a['means']['token'][k])} | {f(p['mean_diff'])} [{f(p['ci95'][0])}, {f(p['ci95'][1])}] | "
                     f"{f(p['median_diff'])} | {f(p['sign_test_p_two_sided'], 4) if p['sign_test_p_two_sided'] is not None else '—'} |")
        L += ["", f"- q_V (diagnostic only): sentence {f(a['means']['sentence']['q_V'])}, token {f(a['means']['token']['q_V'])}",
              f"- raw vs normalised sign disagreement (V_J vs A_VJ), pools: {a['raw_vs_normalised_sign_disagreement_pools'] or 'none'}", ""]
        if att != SON:
            L += ["*Not security evidence at the token level: this attacker was not designed for isolated tokens.*", ""]
    r = S["resources"]
    L += ["## Resources (one-shot Sonnet, every provider row: original, resend, repair)", "",
          "| condition | rows | input tokens | output tokens | cost (credit) | at 128k | refused for credit |", "|---|---|---|---|---|---|---|"]
    for c, v in r.items():
        L.append(f"| {c} | {v['requests_rows']} | {v['input_tokens']:,} | {v['output_tokens']:,} | ${v['cost_usd']:.2f} | "
                 f"{v['at_128k']} | {v['refused_for_credit']} |")
    if "descriptive_excerpt_vs_headline_F1_J" in S:
        d = S["descriptive_excerpt_vs_headline_F1_J"]
        L += ["", f"Descriptive only (common metric F1_J): excerpt sentence arm {f(d['excerpt_sentence_arm_F1_J_mean'])} vs "
              f"full-document headline {f(d['headline_full_document_F1_J_mean'])}."]
    L += ["", "## Claim discipline", "",
          "Supports at most: on identical four-sentence excerpts from seven-document pools of PMC clinical case reports, "
          "single-token fragmentation reduced / changed null-adjusted visible joint reconstruction under the frozen "
          "one-shot Sonnet attacker relative to sentence fragmentation. It does not support: 'secure', 'prevents "
          "reconstruction', a threshold, a semantic-context mechanism, or generalisation beyond this corpus, task, "
          "attacker and resource budget. RBNC is resource-bounded non-completion, never a zero score; the complete-case "
          "paired analysis may be biased in an unknown direction. The RBNC projection made before the run was a "
          "model-based extrapolation, not an observed probability."]
    open(os.path.join(out_dir, "RESULTS.md"), "w", encoding="utf-8").write("\n".join(L) + "\n")


def selftest():
    """Synthetic answers built from the frozen truth (no attacker, no provider)."""
    tmp = tempfile.mkdtemp(prefix="ste_selftest_")
    try:
        rng = random.Random(7)
        for cond in CELLS:
            d = os.path.join(tmp, "final", "singleTokenEdgeJ", os.path.basename(CELLS[cond]))
            os.makedirs(d)
            with open(os.path.join(d, "J.jsonl"), "w", encoding="utf-8") as fj, \
                    open(os.path.join(d, "J.rbnc.jsonl"), "w", encoding="utf-8") as fr:
                for k, (pid, m) in enumerate(POOLS):
                    ps, _key, truth = scorer(cond, pid, m)
                    if cond == "token" and k % 4 == 0:
                        fr.write(json.dumps({"unit": pid}) + "\n")
                        continue
                    gs = [list(v) for v in truth[pid].values()]
                    corr = 0.1 if cond == "sentence" else 0.4
                    for g in gs:
                        idx = rng.sample(range(len(g)), int(corr * len(g)))
                        vals_ = [g[i] for i in idx]
                        rng.shuffle(vals_)
                        for i, v in zip(idx, vals_):
                            g[i] = v
                    fj.write(json.dumps({"game": "J", "unit": pid, "alias_map": {f: f for f in ps.all_ids},
                                         "raw_response": gs, "repair": {"policy_share": 0.0}}) + "\n")
        loc = os.path.join(tmp, "local")
        os.makedirs(loc)
        for att, stem in LOCAL_FILE.items():
            for cond in CELLS:
                with open(os.path.join(loc, f"{stem}__{os.path.basename(CELLS[cond])}.jsonl"), "w", encoding="utf-8") as fh:
                    for pid, m in POOLS:
                        ps, _k, _t = scorer(cond, pid, m)
                        ids = ps.all_ids[:]
                        rng.shuffle(ids)
                        fh.write(json.dumps({"pool": pid, "reconstruction": [ids[i::7] for i in range(7)],
                                             "F1_J": 0.1, "F1_L": 0.2, "q": 0.5, "b_J": 0.1, "A_J": 0.0}) + "\n")
        S = run(os.path.join(tmp, "final"), loc, os.path.join(tmp, "none*.jsonl"), os.path.join(tmp, "out"), 200)
        a = S["attackers"][SON]
        ok = (a["n_complete"]["token"] == 15 and len(a["rbnc"]["token"]) == 5 and a["n_effective"] == 15
              and os.path.exists(os.path.join(tmp, "out", "RESULTS.md")))
        print(f"SELFTEST {'PASSED' if ok else 'FAILED'}: synthetic Sonnet token completion {a['n_complete']['token']}/20, "
              f"RBNC {len(a['rbnc']['token'])}, n_effective {a['n_effective']}, primary paired mean "
              f"{a['paired_sentence_minus_token']['A_VJ']['mean_diff']:.3f} (synthetic, meaningless)")
        if not ok:
            sys.exit(1)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        selftest()
        return
    S = run("results/final", "results/single_token_edge/local", "results/batches/single-token-edge-J*.results.jsonl",
            "results/single_token_edge/analysis", N_PERM)
    print(open("results/single_token_edge/analysis/RESULTS.md", encoding="utf-8").read())


if __name__ == "__main__":
    main()
