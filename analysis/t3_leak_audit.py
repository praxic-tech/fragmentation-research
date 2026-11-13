"""
t3_leak_audit.py — can the tier 3 numbers come from anything but the fragment
text? The tier 0 leak checks (analysis/t0_leak_audit.py,
analysis/t0_unmasked_control.py), repeated for T3-crossenc as RUN_DECISIONS
D19 requires. Reads the verified evaluation pair scores and the frozen pools;
writes only results/final_t3/LEAK_AUDIT.{json,txt}. Scores nothing new for
the paper.

Why no GPU is needed. The model sees two texts and nothing else, and
score_texts scores each distinct text pair once, in an order fixed by the
sorted set of distinct texts. Showing the same fragments in another order, or
under other labels, therefore gives the same matrices with rows and columns
permuted, bit for bit. Every condition below takes the stored matrices of a
unit, permutes them into the order that condition presents, and runs the
frozen decoder exactly as runs/final_t3.py does. A fragment-blind model is a
constant: identical texts get identical logits in every pair, so P - P^T = 0
and the same-document probability is the same everywhere; zero logits are
that case (the decoder is invariant to the constant's value).

 0. Machinery check. The permutation path with the reported seeds must
    reproduce every reported reconstruction (382 pools, 370 documents).
 1. Text-blind. Constant scores, masked presentation as reported. Must be
    chance: Game O tau ~ 0, Game J q ~ 0.5, F1_J near the one-bucket base.
 2. Masked vs unmasked. Raw fragment ids, which spell out the true order,
    sorted, so every index-order tie falls to the truth. Equal scores = no
    path from ids or presentation into the result.
    Positive controls: (a) the T3 decoder itself, text-blind and unmasked:
    its tie rule hands it the truth, so this must score high, showing the
    test detects the leak it is for; (b) the Jaccard orderers (tier 0 run,
    results/final_t0_ext/UNMASKED_CONTROL.json), quoted.
 3. Presentation invariance. 10 other shuffle / mask seeds (as tier 0).
 4. Ties. Within-unit pairs with exactly zero before-logit (only the alias
    order decides them) and with identical texts.
 5. Pipeline markers in every text the model scored.
 6. Contamination. The fine-tuning corpus hash must equal the corpus the
    tier 0 8-gram audit scanned; that audit's numbers are quoted.

    python analysis/t3_leak_audit.py [--scores models/t3]
"""

import argparse
import hashlib
import json
import os
import random
import re
import statistics
import sys
import time
from collections import Counter, defaultdict, deque

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
for d in ("adversaries", "harness", "analysis", "runs"):
    sys.path.insert(0, os.path.join(ROOT, d))
sys.stdout.reconfigure(encoding="utf-8")

import numpy as np                                             # noqa: E402

import harness as H                                            # noqa: E402
import crossenc_t3 as T3                                       # noqa: E402
import t3_units as U                                           # noqa: E402
import final_t3 as R                                           # noqa: E402
from joint_game import _unit_seed, score_row                   # noqa: E402

OUT = R.OUT
ALT_SEEDS = [1, 2, 3, 5, 8, 13, 21, 34, 55, 89]                # as tier 0
SEED = U.SEED


# ── score matrices under another presentation ─────────────────────────────────

def perm(base, new):
    """p with new[k] == base[p[k]]; repeated texts matched in turn (their rows are identical)."""
    where = defaultdict(deque)
    for i, t in enumerate(base):
        where[t].append(i)
    p = np.array([where[t].popleft() for t in new])
    assert not any(where.values()) and len(p) == len(base)
    return p


def permute(sc, p):
    ix = np.ix_(p, p)
    return {"S": sc["S"][ix], "P": sc["P"][ix], "A": sc["A"][ix], "pos": sc["pos"][p]}


def blind(m):
    z = np.zeros((m, m), dtype=np.float32)
    return {"S": z, "P": z, "A": z, "pos": np.full(m, 0.5, dtype=np.float32)}


def canon(groups):
    return sorted(tuple(g) for g in groups)


# ── Game J ────────────────────────────────────────────────────────────────────

def j_load(store):
    units = []
    for game, cell, pid, members in U.j_units():
        frags, key, truth, shown, n_docs, ms = U.j_prepare(cell, pid, members)
        texts = U.j_texts(shown, ms)
        units.append({"game": game, "cell": U.cell_name(cell), "pid": pid, "frags": frags, "key": key,
                      "truth": truth, "n_docs": n_docs, "texts": texts, "sc": T3.store_load(store, texts),
                      "order_seed": _unit_seed(frags, SEED, "order"), "mask_seed": ms})
    return units


def j_decode(u, layout, scores, order_seed=None, mask_seed=None):
    """layout 'masked': shuffle + mask as the attacker is run; 'raw': raw ids sorted (true order)."""
    if layout == "masked":
        shown = [{"fragment_id": f["fragment_id"], "text": f["text"]} for f in u["frags"]]
        random.Random(order_seed).shuffle(shown)
        ids, texts, back = T3.masked_view(shown, SEED, mask_seed)
        labels = [back[i] for i in ids]
    else:
        labels = sorted(f["fragment_id"] for f in u["frags"])
        tx = {f["fragment_id"]: f["text"] for f in u["frags"]}
        texts = [tx[i] for i in labels]
    sc = blind(len(texts)) if scores == "blind" else permute(u["sc"], perm(u["texts"], texts))
    groups = T3.decode(sc, u["n_docs"], R.FROZEN, seed=SEED)
    return [[labels[i] for i in g] for g in groups]


def j_score(u, groups):
    return score_row({"game": "J", "unit": u["pid"], "alias_map": {f["fragment_id"]: f["fragment_id"] for f in u["frags"]},
                      "raw_response": groups, "repair": {"policy_share": 0.0}}, u["key"], u["truth"])


def summ_j(rows):
    C, K = sum(r["C"] for r in rows), sum(r["K"] for r in rows)
    return {"pools": len(rows), "F1_J": statistics.fmean(r["joint_f1"] for r in rows),
            "base": statistics.fmean(r["joint_baseline"] for r in rows),
            "F1_L": statistics.fmean(r["j_linkage_f1"] for r in rows), "q": C / K if K else None,
            "exact_records": sum(r["exact_records"] for r in rows)}


def j_condition(units, layout, scores, seeds=None, reported=None):
    rows, same = defaultdict(list), 0
    for u in units:
        os_, ms = seeds(u) if seeds else (u["order_seed"], u["mask_seed"])
        g = j_decode(u, layout, scores, os_, ms)
        rows[u["game"]].append(j_score(u, g))
        if reported is not None:
            same += canon(g) == canon(reported[(u["game"], u["cell"], u["pid"])])
    out = {game: summ_j(rs) for game, rs in rows.items()}
    out["all"] = summ_j([r for rs in rows.values() for r in rs])
    if reported is not None:
        out["reconstructions_identical_to_reported"] = same
    return out


# ── Game O ────────────────────────────────────────────────────────────────────

def o_load(store):
    units = []
    for game, cell, rid, frags, key in U.o_units():
        texts = U.o_texts(frags)
        units.append({"game": game, "cell": U.cell_name(cell), "rid": rid, "frags": frags, "key": key,
                      "texts": texts, "sc": T3.store_load(store, texts)})
    return units


def o_orderer(u, scores):
    def t3_borda_o(shown, ltext):                              # as runs/final_t3.make_o_orderer
        ids = sorted(shown)
        texts = [ltext[i] for i in ids]
        sc = blind(len(ids)) if scores == "blind" else permute(u["sc"], perm(u["texts"], texts))
        return [ids[i] for i in T3.order_borda(range(len(ids)), T3.before_logit(sc["P"]))]
    return t3_borda_o


def o_order(u, layout, scores, seed=H.DEFAULT_SEED):
    ids = [f["fragment_id"] for f in u["frags"]]
    text = {f["fragment_id"]: f["text"] for f in u["frags"]}
    fn = o_orderer(u, scores)
    if layout == "masked":
        return H._masked_shuffled_order(fn, ids, text, seed)
    return fn(sorted(ids), text)                               # raw ids, true order (t0_unmasked_control)


def tau_of(u, order):
    return score_row({"game": "O", "unit": u["rid"], "alias_map": {f["fragment_id"]: f["fragment_id"] for f in u["frags"]},
                      "raw_response": order, "repair": {}}, u["key"], {})["tau"]


def o_condition(units, layout, scores, seed=H.DEFAULT_SEED, reported=None):
    taus, same = defaultdict(list), 0
    for u in units:
        o = o_order(u, layout, scores, seed)
        taus[u["game"]].append(tau_of(u, o))
        if reported is not None:
            same += o == reported[(u["game"], u["cell"], u["rid"])]
    out = {g: {"docs": len(t), "mean_tau": statistics.fmean(t), "sd": statistics.pstdev(t)} for g, t in taus.items()}
    allt = [t for ts in taus.values() for t in ts]
    out["all"] = {"docs": len(allt), "mean_tau": statistics.fmean(allt), "sd": statistics.pstdev(allt)}
    if reported is not None:
        out["orders_identical_to_reported"] = same
    return out


def load_reported():
    rj, ro = {}, {}
    for att, store, keyf in ((R.ATT_J, rj, lambda r: (r["game"], r["cell"], r["pool"])),
                             (R.ATT_O, ro, lambda r: (r["game"], r["cell"], r["doc"]))):
        for root, _d, files in os.walk(OUT):
            for f in files:
                if f.endswith(f".{att}.jsonl"):
                    for line in open(os.path.join(root, f), encoding="utf-8"):
                        r = json.loads(line)
                        store[keyf(r)] = r["reconstruction"]
    assert (len(rj), len(ro)) == (U.N_J, U.N_O), (len(rj), len(ro))
    return rj, ro


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scores", default=os.path.join("models", "t3"))
    a = ap.parse_args()
    for f in ("LEAK_AUDIT.json", "LEAK_AUDIT.txt"):
        if os.path.exists(os.path.join(OUT, f)):
            raise SystemExit(f"{OUT}/{f} exists: the first complete audit is kept; nothing re-run.")
    rec, done, store, n_files = R.check_inputs(a.scores)
    print(f"inputs verified: {n_files} score files, weights {rec['model_sha256'][:12]}", flush=True)
    t_start = time.time()
    jl, ol = j_load(store), o_load(store)
    rep_j, rep_o = load_reported()
    res = {"weights_sha256": rec["model_sha256"], "decoder": R.FROZEN, "score_files_verified": n_files}

    def log(k, v):
        res[k] = v
        print(f"[{(time.time() - t_start) / 60:5.1f} min] {k}: {json.dumps(v)}", flush=True)

    # 0. machinery: the permutation path must reproduce the reported run exactly
    m = {"gameJ": j_condition(jl, "masked", "real", reported=rep_j),
         "gameO": o_condition(ol, "masked", "real", reported=rep_o)}
    log("0_machinery_check", m)
    if (m["gameJ"]["reconstructions_identical_to_reported"], m["gameO"]["orders_identical_to_reported"]) != (U.N_J, U.N_O):
        raise SystemExit("STOP: the permutation path does not reproduce the reported run; nothing below is valid")

    # 1. text-blind, masked as reported
    log("1_text_blind", {"gameJ": j_condition(jl, "masked", "blind"), "gameO": o_condition(ol, "masked", "blind")})

    # 2. masked vs unmasked (+ positive controls)
    unm_j = j_condition(jl, "raw", "real", reported=rep_j)
    unm_o = o_condition(ol, "raw", "real", reported=rep_o)
    log("2_unmasked", {"gameJ": unm_j, "gameO": unm_o,
                       "masked_as_reported": {"gameJ_all": m["gameJ"]["all"], "gameO_all": m["gameO"]["all"]},
                       "difference_unmasked_minus_masked": {
                           "gameJ_F1_J": unm_j["all"]["F1_J"] - m["gameJ"]["all"]["F1_J"],
                           "gameJ_q": unm_j["all"]["q"] - m["gameJ"]["all"]["q"],
                           "gameO_tau": unm_o["all"]["mean_tau"] - m["gameO"]["all"]["mean_tau"]}})
    pc = {"T3_text_blind_unmasked": {"gameJ": j_condition(jl, "raw", "blind"), "gameO": o_condition(ol, "raw", "blind")}}
    t0u = json.load(open(os.path.join("results", "final_t0_ext", "UNMASKED_CONTROL.json"), encoding="utf-8"))
    pc["Jaccard_quoted_from_tier0"] = {k: t0u["gameO"][k] for k in ("Jaccard-Greedy", "Jaccard-MST")}
    log("2_positive_controls", pc)

    # 3. presentation invariance
    inv = []
    for s in ALT_SEEDS:
        inv.append({"seed": s,
                    "gameJ": j_condition(jl, "masked", "real", seeds=lambda u, s=s: (s * 7919 + 1, s * 104729 + 3),
                                         reported=rep_j),
                    "gameO": o_condition(ol, "masked", "real", seed=s, reported=rep_o)})
        print(f"  seed {s}: J F1_J {inv[-1]['gameJ']['all']['F1_J']:.4f} "
              f"({inv[-1]['gameJ']['reconstructions_identical_to_reported']}/{U.N_J} identical), "
              f"O tau {inv[-1]['gameO']['all']['mean_tau']:.4f} "
              f"({inv[-1]['gameO']['orders_identical_to_reported']}/{U.N_O} identical)", flush=True)
    fj = [x["gameJ"]["all"]["F1_J"] for x in inv]
    to = [x["gameO"]["all"]["mean_tau"] for x in inv]
    log("3_presentation_invariance", {
        "seeds": inv, "gameJ_F1_J_range": [min(fj), max(fj)], "gameJ_F1_J_sd": statistics.pstdev(fj),
        "gameO_tau_range": [min(to), max(to)], "gameO_tau_sd": statistics.pstdev(to)})

    # 4. ties
    zero = same_text = pairs = 0
    for u in jl + ol:
        Rm = T3.before_logit(u["sc"]["P"])
        n = len(u["texts"])
        iu = np.triu_indices(n, 1)
        zero += int((Rm[iu] == 0).sum())
        pairs += len(iu[0])
        same_text += sum(c * (c - 1) // 2 for c in Counter(u["texts"]).values())
    log("4_ties", {"pairs": pairs, "zero_before_logit": zero, "share": zero / pairs,
                   "identical_text_pairs": same_text})

    # 5. pipeline markers in every text the model scored
    pat = re.compile(r"prose_\d{4}|frag_\d|_frag|PMC\d{5,}|record_id|fragment_id|\bm_\d{7}\b|item_\d", re.I)
    hits, n_txt = Counter(), 0
    for _k, _g, _c, _u, texts in U.all_unit_texts():
        for t in texts:
            n_txt += 1
            hits.update(pat.findall(t))
    log("5_markers", {"texts_scanned": n_txt, "hits": dict(hits.most_common(20))})

    # 6. contamination
    tl = json.load(open(os.path.join(OUT, "train_log.json"), encoding="utf-8"))
    corpus = os.path.join("data", "disjoint_train", "documents.jsonl")
    h = T3.file_sha256(corpus)
    t0a = json.load(open(os.path.join("results", "final_t0_ext", "LEAK_AUDIT.json"), encoding="utf-8"))
    log("6_contamination", {"t3_training_corpus_sha256": tl["data_sha256"], "tier0_audited_corpus": corpus,
                            "tier0_audited_corpus_sha256": h, "same_corpus": tl["data_sha256"] == h,
                            "tier0_8gram_audit": {k: v for k, v in t0a["6_contamination"].items()
                                                  if k != "top5_by_single_train_doc"},
                            "base_model": tl["base_model"], "base_revision": tl["base_revision"]})

    res["wall_minutes"] = round((time.time() - t_start) / 60, 1)
    json.dump(res, open(os.path.join(OUT, "LEAK_AUDIT.json"), "w", encoding="utf-8"), indent=2)

    def j(x):
        return f"F1_J {x['F1_J']:.4f}  base {x['base']:.4f}  F1_L {x['F1_L']:.4f}  q {x['q']:.4f}"
    b, u2, p2 = res["1_text_blind"], res["2_unmasked"], res["2_positive_controls"]["T3_text_blind_unmasked"]
    lines = [
        "TIER 3 LEAK AUDIT (RUN_DECISIONS D19) -- T3-crossenc, frozen decoder, verified evaluation scores",
        f"0 machinery: reported run reproduced  J {m['gameJ']['reconstructions_identical_to_reported']}/{U.N_J}"
        f"  O {m['gameO']['orders_identical_to_reported']}/{U.N_O}",
        f"  as reported        J all  {j(m['gameJ']['all'])}   O tau {m['gameO']['all']['mean_tau']:+.4f}",
        f"1 text-blind         J all  {j(b['gameJ']['all'])}   O tau {b['gameO']['all']['mean_tau']:+.4f}",
        f"2 unmasked (raw ids) J all  {j(u2['gameJ']['all'])}   O tau {u2['gameO']['all']['mean_tau']:+.4f}",
        f"  identical to masked: J {u2['gameJ']['reconstructions_identical_to_reported']}/{U.N_J}"
        f"  O {u2['gameO']['orders_identical_to_reported']}/{U.N_O}",
        f"  + control: T3 text-blind unmasked  J all  {j(p2['gameJ']['all'])}   O tau {p2['gameO']['all']['mean_tau']:+.4f}",
        "  + control: Jaccard (tier 0 run)  " + "  ".join(
            f"{k} {v['tau_masked']:+.4f} -> {v['tau_unmasked']:+.4f}"
            for k, v in res["2_positive_controls"]["Jaccard_quoted_from_tier0"].items()),
        f"3 invariance, {len(ALT_SEEDS)} seeds: J F1_J {min(fj):.4f}-{max(fj):.4f} (sd {statistics.pstdev(fj):.4f}),"
        f"  O tau {min(to):+.4f}-{max(to):+.4f} (sd {statistics.pstdev(to):.4f})",
        f"4 ties: {zero:,} of {pairs:,} pairs with zero before-logit ({zero / pairs:.2e}); "
        f"{same_text:,} identical-text pairs",
        f"5 markers: {n_txt:,} texts scanned, hits {dict(hits.most_common(5)) or 'none'}",
        f"6 contamination: training corpus is the tier-0-audited corpus: {res['6_contamination']['same_corpus']}; "
        f"8-gram share in train median {t0a['6_contamination']['median_share_in_train']:.4f}, "
        f"max {t0a['6_contamination']['max_share']:.4f}, docs over 20% {t0a['6_contamination']['docs_over_20pct']}",
        "", "per game (J F1_J / q; O tau):"]
    for g in [x for x, _ in U.J_GAMES]:
        lines.append(f"  {g:<18} reported {m['gameJ'][g]['F1_J']:.4f}/{m['gameJ'][g]['q']:.4f}"
                     f"  blind {b['gameJ'][g]['F1_J']:.4f}/{b['gameJ'][g]['q']:.4f} (base {b['gameJ'][g]['base']:.4f})"
                     f"  unmasked {u2['gameJ'][g]['F1_J']:.4f}/{u2['gameJ'][g]['q']:.4f}"
                     f"  blind+unmasked {p2['gameJ'][g]['F1_J']:.4f}/{p2['gameJ'][g]['q']:.4f}")
    for g in [x for x, _ in U.O_GAMES]:
        lines.append(f"  {g:<18} reported {m['gameO'][g]['mean_tau']:+.4f}  blind {b['gameO'][g]['mean_tau']:+.4f}"
                     f"  unmasked {u2['gameO'][g]['mean_tau']:+.4f}  blind+unmasked {p2['gameO'][g]['mean_tau']:+.4f}")
    lines.append(f"\nwall time {res['wall_minutes']} min")
    open(os.path.join(OUT, "LEAK_AUDIT.txt"), "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
