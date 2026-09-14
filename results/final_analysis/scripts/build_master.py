"""
build_master.py — the master dataset (results plan §1, §30): one row per
independent unit x attacker x condition, full precision. No API calls.

Units: game J -> pool; game O -> document (§2).
Sources, all committed or on disk:
  one-shot Sonnet   results/final/<game>/<cell>/{J,O}.jsonl (+ .rbnc.jsonl), rescored
                    with joint_game.score_row; tokens and cost from every
                    provider result row for the unit (results/batches/final-*)
  Memon-inspired    results/final_free/ (SHA-256-seeded canonical run, D13)
  O floors          results/final_o_floors/ (Jaccard-Greedy, Jaccard-MST, Random)
  baselines         analytic one-bucket (per pool, exact); schema-order
                    (results/audit/identifier_schema_baseline.json, D11);
                    identifier Random (D11/D13: 10,000 seeded draws per pool)
Pool 1 (screening) is NOT in this dataset (§24); it stays in results/grid_A_scored.

    python results/final_analysis/scripts/build_master.py
"""

import csv
import glob
import hashlib
import json
import os
import random
import statistics as st
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.dirname(HERE)
ROOT = os.path.dirname(os.path.dirname(PKG))
os.chdir(ROOT)
for d in ("adversaries", "harness", "analysis"):
    sys.path.insert(0, os.path.join(ROOT, d))

from batch_game import at_ceiling                        # noqa: E402
from batch_submit import make_custom_id                  # noqa: E402
from joint_game import _as_groups, build_units, score_row  # noqa: E402
from joint_metrics import decompose, score_joint         # noqa: E402

J_SPECS = {"headline": ["runs/final_headlineJ.json"],
           "grid": [f"runs/final_gridJ_w{k}.json" for k in (1, 2, 3, 4)],
           "identifier": ["runs/final_identifierJ.json"]}
O_SPECS = {"headline": ["runs/final_headlineO.json"],
           "grid": [f"runs/final_gridO_w{k}.json" for k in (1, 2, 3)]}
RESULT_DIR = {("headline", "J"): "headlineJ", ("grid", "J"): "gridJ", ("identifier", "J"): "identifierJ",
              ("headline", "O"): "headlineO", ("grid", "O"): "gridO"}
IN_PRICE, OUT_PRICE = 1.0, 5.0            # $/M tokens, the batch rate the ledger settles at
RANDOM_DRAWS, SEED = 10_000, 42


def words(t):
    return len(t.split())


def cell_meta(cell_dir):
    base = os.path.basename(os.path.normpath(cell_dir))
    if base == "prose":
        return "prose", "semantic", "sentence", "semantic__sentence (full length)"
    if base.startswith("identifier"):
        return "identifier", "field", "field", base
    s, g = base.split("__")
    return "prose", s, g, base


def usage_index():
    """Per custom id: summed usage over every provider row, and its history."""
    idx = defaultdict(lambda: {"in": 0, "out": 0, "retry": False, "refused": False, "repaired": False,
                               "rows": 0, "ceiling": False, "out_answer": 0, "out_repair": 0})
    for p in glob.glob("results/batches/final-*.results.jsonl"):
        tag = os.path.basename(p).replace(".results.jsonl", "")
        for l in open(p, encoding="utf-8"):
            if not l.strip():
                continue
            r = json.loads(l)
            cid = r["custom_id"][:-3] if r["custom_id"].endswith("-r1") else r["custom_id"]
            e = idx[cid]
            e["rows"] += 1
            u = r.get("usage") or {}
            e["in"] += u.get("input_tokens", 0) or 0
            e["out"] += u.get("output_tokens", 0) or 0
            # per CALL: the 128k budget applies to each call, not to a unit's total
            e["out_repair" if "-r1" in tag else "out_answer"] += u.get("output_tokens", 0) or 0
            if "credit balance is too low" in str(r.get("error")):
                e["refused"] = True
            if tag.endswith("-rs1") and "-r1" not in tag:
                e["retry"] = True
            if "-r1" in tag:
                e["repaired"] = True
            if at_ceiling(r):
                e["ceiling"] = True
    return idx


def frag_stats(frags):
    fw = [words(f["text"]) for f in frags]
    return {"n_fragments": len(frags), "frag_words_mean": st.fmean(fw), "frag_words_median": st.median(fw),
            "frag_words_sd": st.pstdev(fw), "frag_words_min": min(fw), "frag_words_max": max(fw),
            "frag_chars_mean": st.fmean(len(f["text"]) for f in frags)}


def pool_covariates(frags, members):
    by = defaultdict(list)
    for f in frags:
        by[f["record_id"]].append(f)
    dw = [sum(words(f["text"]) for f in by[m]) for m in members]
    dc = [sum(len(f["text"]) for f in by[m]) for m in members]
    fs = frag_stats(frags)
    return {"n_docs": len(members), **fs, "frags_per_doc": len(frags) / len(members),
            "doc_words_mean": st.fmean(dw), "doc_words_median": st.median(dw), "doc_words_min": min(dw),
            "doc_words_max": max(dw), "pool_words_total": sum(dw), "doc_chars_mean": st.fmean(dc),
            "frags_per_1000_words": 1000 * len(frags) / sum(dw)}


def j_metrics(r):
    """score_row output -> the §3 fields."""
    C, K, G, T = r["C"], r["K"], r["pairs_guessed"], r["pairs_true"]
    return {"precision_J": r["joint_p"], "recall_J": r["joint_r"], "F1_J": r["joint_f1"],
            "b_J": r["joint_baseline"], "A_J": r["joint_advantage"], "F1_L": r["j_linkage_f1"],
            "L_precision": r["l_precision"], "L_recall": r["l_recall"], "q": r["q"], "C": C, "K": K,
            "pairs_guessed": G, "pairs_true": T, "TP_directed": C, "FP_directed": G - C,
            "FN_directed": T - C, "exact_records": r["exact_records"], "exact_rate": r["exact_rate"],
            "n_pred_clusters": r["n_groups_guessed"], "n_dropped": r.get("n_dropped", 0),
            "identity_residual": (abs(r["joint_f1"] - r["j_linkage_f1"] * r["q"])
                                  if r["q"] is not None else None)}


def random_identifier(frags, members, key, seed):
    """D11/D13: shuffle, deal round-robin into the known N groups, keep the dealt order."""
    rng = random.Random(seed)
    ids = [f["fragment_id"] for f in frags]
    rec = {f["fragment_id"]: f["record_id"] for f in frags}
    acc = defaultdict(float)
    qs, Cs, Ks = [], 0, 0
    for _ in range(RANDOM_DRAWS):
        rng.shuffle(ids)
        groups = [ids[i::len(members)] for i in range(len(members))]
        same = tot = 0
        for g in groups:
            for i in range(len(g)):
                for j in range(i + 1, len(g)):
                    tot += 1
                    same += rec[g[i]] == rec[g[j]]
        acc["L_precision"] += same / tot if tot else 0.0
        jp = score_joint(groups, key, list(members))
        dec = decompose(groups, key, list(members))
        acc["F1_J"] += jp["f1"]
        acc["precision_J"] += jp["precision"]
        acc["recall_J"] += jp["recall"]
        acc["F1_L"] += dec["f1_linkage"]
        Cs += dec["C"]
        Ks += dec["K"]
        if dec["q"] is not None:
            qs.append(dec["q"])
    out = {k: v / RANDOM_DRAWS for k, v in acc.items()}
    out.update({"q": st.fmean(qs) if qs else None, "C": Cs / RANDOM_DRAWS, "K": Ks / RANDOM_DRAWS,
                "expectation": f"mean of {RANDOM_DRAWS} seeded draws"})
    return out


def main():
    use = usage_index()
    rows = []
    schema = {p["pool"]: p for p in json.load(open("results/audit/identifier_schema_baseline.json",
                                                   encoding="utf-8"))["pools"]}

    # ── game J ──────────────────────────────────────────────────────────────
    for fam, paths in J_SPECS.items():
        for path in paths:
            b = json.load(open(path, encoding="utf-8"))["build"]
            for cell_dir in b["cells"]:
                corpus, strat, gran, cell = cell_meta(cell_dir)
                base = os.path.basename(os.path.normpath(cell_dir))
                rdir = os.path.join("results", "final", RESULT_DIR[(fam, "J")], base)
                sonnet = {r["unit"]: r for r in (json.loads(l) for l in
                          open(os.path.join(rdir, "J.jsonl"), encoding="utf-8") if l.strip())}
                rbnc = {r["unit"] for r in (json.loads(l) for l in
                        open(os.path.join(rdir, "J.rbnc.jsonl"), encoding="utf-8") if l.strip())} \
                    if os.path.exists(os.path.join(rdir, "J.rbnc.jsonl")) else set()
                memon = {r["pool"]: r for r in (json.loads(l) for l in open(
                    os.path.join("results", "final_free", RESULT_DIR[(fam, "J")],
                                 f"{base}.memon_joint.jsonl"), encoding="utf-8") if l.strip())}
                for pid, members in b["pools"]:
                    _o, units, key, truth = build_units(cell_dir, 0, len(members), SEED,
                                                        pools=[(pid, members)], o_docs=[])
                    (_p, frags, _n), = units
                    common = {"corpus": corpus, "game": "J", "family": fam, "cell": cell,
                              "strategy": strat, "granularity": gran, "unit_id": pid,
                              "designation": {"headline": "headline", "grid": "primary",
                                              "identifier": "identifier-primary"}[fam],
                              **pool_covariates(frags, members)}
                    tg = truth[pid]
                    # analytic one-bucket baseline: exact; q is its expected value 1/2
                    any_scored = score_row({"game": "J", "unit": pid,
                                            "alias_map": {f["fragment_id"]: f["fragment_id"] for f in frags},
                                            "raw_response": [[f["fragment_id"] for f in frags]],
                                            "repair": {"policy_share": 0.0}}, key, truth)
                    rows.append({**common, "attacker": "Analytic one-bucket", "completion": "completed",
                                 "F1_J": any_scored["joint_baseline"], "b_J": any_scored["joint_baseline"],
                                 "A_J": 0.0, "F1_L": any_scored["baseline"], "q": 0.5,
                                 "note": "exact analytic value; q is the expected value of an arbitrary order"})
                    if fam == "identifier":
                        s = schema[pid]
                        rows.append({**common, "attacker": "Schema-order", "completion": "completed",
                                     "F1_J": s["schema_joint_f1"], "b_J": s["analytic_joint_baseline"],
                                     "A_J": (s["schema_joint_f1"] - s["analytic_joint_baseline"])
                                     / (1 - s["analytic_joint_baseline"]),
                                     "F1_L": s["schema_linkage_f1"], "q": s["schema_q"],
                                     "note": "D11 schema-order baseline (truth-free)"})
                        pool_seed = int(hashlib.sha256(f"{SEED}|random-identifier|{pid}".encode()).hexdigest()[:16], 16)
                        rnd = random_identifier(frags, members, key, pool_seed)
                        bj = any_scored["joint_baseline"]
                        rows.append({**common, "attacker": "Random", "completion": "completed", **rnd,
                                     "b_J": bj, "A_J": (rnd["F1_J"] - bj) / (1 - bj),
                                     "note": "D11/D13 random identifier baseline"})
                    # Memon-inspired
                    m = memon[pid]
                    rows.append({**common, "attacker": "Memon-inspired", "completion": "completed",
                                 **j_metrics(m), "cluster_sizes": json.dumps(sorted(
                                     (len(g) for g in m["reconstruction"]), reverse=True)),
                                 "context_coverage": m["context_coverage"],
                                 "cost_usd": 0.0, "input_tokens": 0, "output_tokens": 0})
                    # one-shot Sonnet
                    cid = make_custom_id(base, "J", pid)
                    u = use.get(cid, {"in": 0, "out": 0, "retry": False, "refused": False,
                                      "repaired": False, "ceiling": False})
                    res = {"input_tokens": u["in"], "output_tokens": u["out"],
                           "cost_usd": u["in"] / 1e6 * IN_PRICE + u["out"] / 1e6 * OUT_PRICE,
                           "answer_call_output_tokens": u.get("out_answer"),
                           "repair_call_output_tokens": u.get("out_repair"),
                           "transport_retry": u["retry"], "provider_refusal": u["refused"],
                           "repaired": u["repaired"]}
                    if pid in rbnc:
                        rows.append({**common, "attacker": "One-shot Sonnet", "completion": "rbnc",
                                     "rbnc": True, **res, "note": "D6: 128k exhausted; not scored, not F1=0"})
                        continue
                    r = sonnet[pid]
                    sc = score_row(r, key, truth)
                    alias = r["alias_map"]
                    groups = [[alias[x] for x in g if x in alias] for g in _as_groups(r["raw_response"])]
                    groups = [g for g in groups if g]
                    rep = r.get("repair") or {}
                    rows.append({**common, "attacker": "One-shot Sonnet", "completion": "completed",
                                 "rbnc": False, **res, **j_metrics(sc),
                                 "malformed_first_answer": bool(rep.get("calls", 1) > 1),
                                 "cluster_sizes": json.dumps(sorted((len(g) for g in groups), reverse=True)),
                                 "prompt_chars": len(r["prompt"])})

    # ── game O ──────────────────────────────────────────────────────────────
    floors = defaultdict(dict)
    for p in glob.glob("results/final_o_floors/*/*.jsonl"):
        for l in open(p, encoding="utf-8"):
            if l.strip():
                r = json.loads(l)
                floors[(r["game"], r["cell"], r["doc"])][r["attacker"]] = r
    for fam, paths in O_SPECS.items():
        for path in paths:
            b = json.load(open(path, encoding="utf-8"))["build"]
            for cell_dir in b["cells"]:
                corpus, strat, gran, cell = cell_meta(cell_dir)
                base = os.path.basename(os.path.normpath(cell_dir))
                rdir = os.path.join("results", "final", RESULT_DIR[(fam, "O")], base)
                sonnet = {r["unit"]: r for r in (json.loads(l) for l in
                          open(os.path.join(rdir, "O.jsonl"), encoding="utf-8") if l.strip())}
                o_units, _p, key, _t = build_units(cell_dir, 0, 7, SEED, pools=[], o_docs=b["o_docs"])
                for rid, frags, _n in o_units:
                    truth = key[rid]
                    common = {"corpus": corpus, "game": "O", "family": fam, "cell": cell, "strategy": strat,
                              "granularity": gran, "unit_id": rid,
                              "designation": "headline" if fam == "headline" else "primary",
                              "n_docs": 1, **frag_stats(frags), "frags_per_doc": len(frags),
                              "doc_words_mean": sum(words(f["text"]) for f in frags),
                              "doc_chars_mean": sum(len(f["text"]) for f in frags),
                              "frags_per_1000_words": 1000 * len(frags) / sum(words(f["text"]) for f in frags)}
                    r = sonnet[rid]
                    sc = score_row(r, key, {})
                    alias = r["alias_map"]
                    g = _as_groups(r["raw_response"])
                    order = [alias[x] for x in (g[0] if g else []) if x in alias]
                    pos = {f: i for i, f in enumerate(truth)}
                    disp = sorted(abs(i - pos[f]) for i, f in enumerate(order)) if not sc.get("malformed") else []
                    cid = make_custom_id(base, "O", rid)
                    u = use.get(cid, {"in": 0, "out": 0, "retry": False, "refused": False, "repaired": False})
                    rows.append({**common, "attacker": "One-shot Sonnet",
                                 "completion": "malformed" if sc.get("malformed") else "completed",
                                 "rbnc": False, "tau": sc.get("tau"),
                                 "pairs_correct": (1 + sc["tau"]) / 2 if sc.get("tau") is not None else None,
                                 "exact_order": order == truth, "exact_fraction": sc.get("exact_fraction"),
                                 "mean_abs_disp": st.fmean(disp) if disp else None,
                                 "median_abs_disp": st.median(disp) if disp else None,
                                 "max_abs_disp": max(disp) if disp else None,
                                 "longest_run": sc.get("longest_run"), "run_fraction": sc.get("run_fraction"),
                                 "input_tokens": u["in"], "output_tokens": u["out"],
                                 "cost_usd": u["in"] / 1e6 * IN_PRICE + u["out"] / 1e6 * OUT_PRICE,
                           "answer_call_output_tokens": u.get("out_answer"),
                           "repair_call_output_tokens": u.get("out_repair"),
                                 "transport_retry": u["retry"], "provider_refusal": u["refused"],
                                 "repaired": u["repaired"], "prompt_chars": len(r["prompt"])})
                    for name in ("Jaccard-Greedy", "Jaccard-MST", "Random"):
                        f = floors[(RESULT_DIR[(fam, "O")], base, rid)][name]
                        rows.append({**common, "attacker": name, "completion": "completed",
                                     **{k: f.get(k) for k in ("tau", "pairs_correct", "exact_order",
                                                              "exact_probability", "exact_fraction",
                                                              "mean_abs_disp", "median_abs_disp",
                                                              "max_abs_disp", "longest_run", "run_fraction")},
                                     "cost_usd": 0.0, "note": f.get("expectation", "")})

    cols = []
    for r in rows:
        for k in r:
            if k not in cols:
                cols.append(k)
    os.makedirs(PKG, exist_ok=True)

    def dump(name, sel):
        with open(os.path.join(PKG, name), "w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=cols)
            w.writeheader()
            for r in sel:
                w.writerow({k: ("" if v is None else v) for k, v in r.items()})
        return len(sel)

    n = dump("MASTER_RESULTS.csv", rows)
    dump("HEADLINE_J.csv", [r for r in rows if r["game"] == "J" and r["family"] == "headline"])
    dump("GRID_J.csv", [r for r in rows if r["game"] == "J" and r["family"] == "grid"])
    dump("IDENTIFIER_J.csv", [r for r in rows if r["game"] == "J" and r["family"] == "identifier"])
    dump("GAME_O.csv", [r for r in rows if r["game"] == "O"])
    with open(os.path.join(PKG, "HIERARCHICAL.csv"), "w", encoding="utf-8", newline="") as fh:
        fh.write("status\nPENDING -- the hierarchical run has not been launched (RUN_DECISIONS D13); "
                 "this file is filled when it is\n")
    counts = defaultdict(int)
    for r in rows:
        counts[(r["game"], r["family"], r["attacker"], r["completion"])] += 1
    for k in sorted(counts):
        print(f"  {k}: {counts[k]}")
    resid = [r["identity_residual"] for r in rows if r.get("identity_residual") is not None]
    print(f"MASTER_RESULTS.csv: {n} rows; F1_J = F1_L x q identity max residual {max(resid):.2e}")


if __name__ == "__main__":
    main()
