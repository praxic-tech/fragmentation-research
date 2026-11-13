"""
t0_leak_audit.py — can the tier 0 numbers come from anything but the fragment
text? (RUN_DECISIONS D19.) Reads the frozen pools; writes only
results/final_t0_ext/LEAK_AUDIT.{md,json}. Scores nothing new for the paper.

The leak D1 found: the Jaccard orderers' similarity was 0 for most pairs, so
almost every step was a tie, and ties fell to the raw id / list position,
which reproduce the true order (MST tau 0.70 as run, -0.02 masked). Any
attacker whose ties or inputs carry order can look good for the same reason.

 1. Text-blind control. Same code path, same presentation, but every
    fragment's text replaced by the same string. Whatever the attacker scores
    now can only come from ids, aliases or presentation order. Must be chance:
    Game O tau ~ 0, Game J q ~ 0.5.
 2. Order-blind control (J). Real text for grouping, but the position model
    replaced by a constant, so order comes only from ties -> aliases. q ~ 0.5.
 3. Presentation invariance. Re-run with 10 other shuffle / mask seeds. The
    position sort depends on the text alone, so Game O orders should be
    identical apart from exact ties, and J scores should not move.
 4. Ties. Share of within-unit pairs with exactly equal predicted position
    (those are the only pairs an alias decides).
 5. Pipeline markers. Do fragment texts contain ids, record ids, PMCIDs or
    "frag" tokens?
 6. Training contamination beyond PMCID. Word 8-gram containment of every
    evaluation document in the training+dev corpus, and its best single
    training document (catches re-published or duplicated case reports).

    python analysis/t0_leak_audit.py
"""

import glob
import hashlib
import json
import os
import random
import re
import statistics
import sys
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
for d in ("adversaries", "harness", "analysis", "runs"):
    sys.path.insert(0, os.path.join(ROOT, d))
sys.stdout.reconfigure(encoding="utf-8")

import numpy as np                                             # noqa: E402

import harness as H                                            # noqa: E402
import classical_t0 as T0                                      # noqa: E402
from joint_game import _unit_seed, build_units, score_row      # noqa: E402
import final_t0_attacker as F                                  # noqa: E402
import final_t0_extended as X                                  # noqa: E402

OUT = os.path.join("results", "final_t0_ext")
ALT_SEEDS = [1, 2, 3, 5, 8, 13, 21, 34, 55, 89]
BLANK = "the patient was seen"


class ConstPos:
    alpha = None

    def predict(self, texts):
        return np.zeros(len(list(texts)))


def headline_j_units():
    b = json.load(open("runs/final_headlineJ.json", encoding="utf-8"))["build"]
    cell = b["cells"][0]
    for pid, members in b["pools"]:
        _o, units, key, truth = build_units(cell, 0, len(members), 42, pools=[(pid, members)], o_docs=[])
        (_p, frags, n_docs), = units
        yield pid, frags, n_docs, key, truth


def j_score(pid, frags, n_docs, key, truth, pos, k, c, order_seed, mask_seed, blank=False):
    shown = [{"fragment_id": f["fragment_id"], "text": BLANK if blank else f["text"]} for f in frags]
    random.Random(order_seed).shuffle(shown)
    groups, _ = T0.attack_classical(shown, n_docs, pos, k, c, seed=42, mask_seed=mask_seed)
    return score_row({"game": "J", "unit": pid, "alias_map": {f["fragment_id"]: f["fragment_id"] for f in frags},
                      "raw_response": groups, "repair": {"policy_share": 0.0}}, key, truth)


def summ_j(rows):
    C, K = sum(r["C"] for r in rows), sum(r["K"] for r in rows)
    return {"F1_J": statistics.fmean(r["joint_f1"] for r in rows),
            "F1_L": statistics.fmean(r["j_linkage_f1"] for r in rows), "q": C / K if K else None}


def o_tau(fn, ids, text, key, rid, seed):
    order = H._masked_shuffled_order(fn, ids, text, seed)
    r = score_row({"game": "O", "unit": rid, "alias_map": {i: i for i in ids},
                   "raw_response": order, "repair": {}}, key, {})
    return r["tau"], order


def shingles(text, n=8):
    w = re.findall(r"[a-z0-9]+", text.lower())
    return {hashlib.blake2b(" ".join(w[i:i + n]).encode(), digest_size=8).digest() for i in range(len(w) - n + 1)}


def main():
    pos, k, c, sha = F.load_classical()
    res = {"position_model_sha256": sha}
    o_units = list(X.o_units())
    head_o = [u for u in o_units if u[0] == "headlineO"]
    jl = list(headline_j_units())

    # 1. text-blind control -------------------------------------------------
    orderers = X.make_orderers(pos)
    blind = {}
    for att, fn in orderers.items():
        taus = []
        for game, cell, rid, frags, key in o_units:
            ids = [f["fragment_id"] for f in frags]
            t, _ = o_tau(fn, ids, {i: BLANK for i in ids}, key, rid, H.DEFAULT_SEED)
            taus.append(t)
        blind[att] = {"docs": len(taus), "mean_tau": statistics.fmean(taus),
                      "sd": statistics.pstdev(taus)}
    rows = [j_score(pid, fr, n, key, tr, pos, k, c, _unit_seed(fr, 42, "order"), _unit_seed(fr, 42, "labels"), blank=True)
            for pid, fr, n, key, tr in jl]
    blind["T0-classical J headline"] = summ_j(rows)
    res["1_text_blind"] = blind
    print("1 text-blind:", json.dumps(blind, indent=1), flush=True)

    # 2. order-blind J -----------------------------------------------------
    rows = [j_score(pid, fr, n, key, tr, ConstPos(), k, c, _unit_seed(fr, 42, "order"), _unit_seed(fr, 42, "labels"))
            for pid, fr, n, key, tr in jl]
    res["2_order_blind_J_headline"] = summ_j(rows)
    print("2 order-blind J:", res["2_order_blind_J_headline"], flush=True)

    # 3. presentation invariance -----------------------------------------------
    fn = orderers["T0-classical-O"]
    base_orders = {}
    base_taus = []
    for game, cell, rid, frags, key in head_o:
        ids = [f["fragment_id"] for f in frags]
        t, o = o_tau(fn, ids, {f["fragment_id"]: f["text"] for f in frags}, key, rid, H.DEFAULT_SEED)
        base_orders[rid], _ = o, base_taus.append(t)
    inv_o = []
    for s in ALT_SEEDS:
        taus, same = [], 0
        for game, cell, rid, frags, key in head_o:
            ids = [f["fragment_id"] for f in frags]
            t, o = o_tau(fn, ids, {f["fragment_id"]: f["text"] for f in frags}, key, rid, s)
            taus.append(t)
            same += o == base_orders[rid]
        inv_o.append({"seed": s, "mean_tau": statistics.fmean(taus), "orders_identical": same, "docs": len(taus)})
    inv_j = []
    for s in ALT_SEEDS[:5]:
        rows = [j_score(pid, fr, n, key, tr, pos, k, c, s * 7919 + 1, s * 104729 + 3) for pid, fr, n, key, tr in jl]
        inv_j.append({"seed": s, **summ_j(rows)})
    res["3_presentation_invariance"] = {"gameO_headline_base_tau": statistics.fmean(base_taus),
                                        "gameO_headline": inv_o, "gameJ_headline": inv_j}
    print("3 invariance O:", inv_o, "\n  J:", inv_j, flush=True)

    # 4. ties ---------------------------------------------------------------
    tie_pairs = all_pairs = 0
    for game, cell, rid, frags, key in o_units:
        p = pos.predict([f["text"] for f in frags])
        cnt = Counter(np.round(p, 12))
        tie_pairs += sum(v * (v - 1) // 2 for v in cnt.values())
        all_pairs += len(p) * (len(p) - 1) // 2
    res["4_ties"] = {"tied_pairs": tie_pairs, "pairs": all_pairs, "share": tie_pairs / all_pairs}
    print("4 ties:", res["4_ties"], flush=True)

    # 5. pipeline markers in fragment text ---------------------------------------
    pat = re.compile(r"prose_\d{4}|frag_\d|_frag|PMC\d{5,}|record_id|fragment_id|\bm_\d{7}\b|item_\d", re.I)
    files = sorted(set(glob.glob("data/prose/prose_fragments.jsonl") + glob.glob("results/grid_A/*/*fragments*.jsonl")
                       + glob.glob("results/identifier_J/*/*fragments*.jsonl") + glob.glob("results/gradient/*/*fragments*.jsonl")
                       + glob.glob("results/single_token_edge/*/*fragments*.jsonl")))
    hits, n_frag = Counter(), 0
    for p in files:
        for line in open(p, encoding="utf-8"):
            t = json.loads(line).get("text", "")
            n_frag += 1
            for m in pat.findall(t):
                hits[m] += 1
    res["5_markers"] = {"files": files, "fragments_scanned": n_frag, "hits": dict(hits.most_common(20))}
    print("5 markers:", n_frag, "fragments in", len(files), "files; hits", dict(hits.most_common(10)), flush=True)

    # 6. contamination beyond PMCID ---------------------------------------------
    owner = {}
    df = Counter()
    for line in open("data/disjoint_train/documents.jsonl", encoding="utf-8"):
        d = json.loads(line)
        sh = shingles(" ".join(d["sentences"]))
        for s in sh:
            owner.setdefault(s, d["pmcid"])
        df.update(sh)
    contain = []
    for line in open("data/prose/prose_documents.jsonl", encoding="utf-8"):
        d = json.loads(line)
        sh = shingles(d["text"])
        if not sh:
            continue
        inside = [s for s in sh if s in df]
        best = Counter(owner[s] for s in inside).most_common(1)
        contain.append({"record_id": d["record_id"], "pmcid": d["source_pmcid"], "shingles": len(sh),
                        "share_in_train": len(inside) / len(sh),
                        "best_train_doc": best[0][0] if best else None,
                        "share_in_best_doc": best[0][1] / len(sh) if best else 0.0})
    shares = sorted(x["share_in_train"] for x in contain)
    best = sorted(contain, key=lambda x: -x["share_in_best_doc"])[:5]
    res["6_contamination"] = {"eval_docs": len(contain), "median_share_in_train": statistics.median(shares),
                              "p95_share": shares[int(0.95 * len(shares))], "max_share": shares[-1],
                              "docs_over_20pct": sum(s > 0.2 for s in shares),
                              "top5_by_single_train_doc": best}
    print("6 contamination:", json.dumps(res["6_contamination"], indent=1), flush=True)

    json.dump(res, open(os.path.join(OUT, "LEAK_AUDIT.json"), "w", encoding="utf-8"), indent=2, default=str)


if __name__ == "__main__":
    main()
