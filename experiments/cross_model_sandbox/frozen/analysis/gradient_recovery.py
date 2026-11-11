"""
gradient_recovery.py — how much CONTIGUOUS ORIGINAL TEXT the attacker ends up
holding, at each granularity of the controlled gradient. NO API CALLS.

WHY NOT "fragments out of fragments"
------------------------------------
Fragments per document runs 4.00 -> 76.04 across the five arms, so a fragment
count is not comparable between them. Every excerpt is exactly the same text,
averaging 76.0 words, so measuring in WORDS is comparable across all five and
reads directly as a percentage of the document.

THE FREE FLOOR, which is the point of the measure
-------------------------------------------------
At sentence granularity each fragment is already ~19 consecutive words that the
attacker never had to reconstruct. With ZERO correct joins they still hold a
19-word contiguous stretch of the original. At one-word granularity they hold
one word. So "recovered text" has a floor that is a property of the CUT, not of
the attacker, and it falls as the cut gets finer.

    floor_words      the longest single fragment of that document -- what you
                     leak by construction, before the attacker does anything
    recovered_words  the longest run of fragments the attacker placed
                     consecutively AND in true order, summed in words (a run of
                     one fragment is just that fragment: the floor)
    lift             recovered_words - floor_words, the attacker's own
                     contribution in words of contiguous text

A RUN is a maximal sequence of fragments inside one predicted group that are
from the same record and consecutive in that record's true order. A fragment
from another document interrupting the sequence breaks the run, which is the
honest reading: a reader of the reconstruction would hit the interloper.

Also reported, because it isolates attacker skill from the cut:
    join_recall      of the (fragments - 1) true adjacent joins in a document,
                     the fraction the attacker actually recovered

Conventions inherited, not reimplemented: fragments placed nowhere become
singleton groups (score_row's reading); labels are mapped through the stored
alias_map and anything invented is dropped.

    python analysis/gradient_recovery.py
"""

import json
import os
import statistics as st
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
for d in ("adversaries", "harness"):
    sys.path.insert(0, os.path.join(ROOT, d))

from joint_game import _as_groups                           # noqa: E402

OUT = os.path.join("results", "gradient", "recovery.json")

# (label, cell dir with the fragments, dir with the scored J predictions)
ARMS = [
    ("sentence", "results/single_token_edge/edge__sentence",
     "results/final/singleTokenEdgeJ/edge__sentence"),
    ("4-word", "results/gradient/edge__w4", "results/final/gradientJ/edge__w4"),
    ("3-word", "results/gradient/edge__w3", "results/final/gradientJ/edge__w3"),
    ("2-word", "results/gradient/edge__w2", "results/final/gradientJ/edge__w2"),
    ("1-word", "results/single_token_edge/edge__token",
     "results/final/singleTokenEdgeJ/edge__token"),
]


def load_jsonl(p):
    return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]


def arm_stats(cell_dir, pred_dir):
    frags = {f["fragment_id"]: f for f in
             load_jsonl(os.path.join(cell_dir, "prose_fragments.jsonl"))}
    key = {r["record_id"]: r["order"] for r in
           load_jsonl(os.path.join(cell_dir, "prose_answer_key.jsonl"))}
    words = {fid: len(f["text"].split()) for fid, f in frags.items()}
    rec_of = {fid: f["record_id"] for fid, f in frags.items()}
    pos_of = {fid: i for ids in key.values() for i, fid in enumerate(ids)}

    per_doc = []
    for row in load_jsonl(os.path.join(pred_dir, "J.jsonl")):
        amap = row["alias_map"]
        groups = [[amap[l] for l in g if l in amap] for g in _as_groups(row["raw_response"])]
        seen, clean = set(), []
        for g in groups:
            h = [f for f in g if f in frags and f not in seen]
            seen.update(h)
            if h:
                clean.append(h)
        docs_here = {rec_of[f] for g in clean for f in g}
        clean += [[f] for f in frags if f not in seen and rec_of[f] in docs_here]

        # longest correct run per record, in fragments and in words
        best_frag, best_words, joins = {}, {}, {}
        for rid in {rec_of[f] for g in clean for f in g}:
            best_frag[rid], best_words[rid], joins[rid] = 0, 0, 0
        for g in clean:
            run_rec, run_n, run_w = None, 0, 0
            for f in g:
                rid = rec_of[f]
                cont = (run_rec == rid and run_n and
                        pos_of[f] == pos_of[prev] + 1)
                if cont:
                    run_n += 1
                    run_w += words[f]
                    joins[rid] = joins.get(rid, 0) + 1
                else:
                    run_rec, run_n, run_w = rid, 1, words[f]
                if run_n > best_frag.get(rid, 0):
                    best_frag[rid] = run_n
                if run_w > best_words.get(rid, 0):
                    best_words[rid] = run_w
                prev = f

        for rid in key:
            if rid not in best_words:
                continue
            ids = key[rid]
            floor = max(words[f] for f in ids)
            total = sum(words[f] for f in ids)
            per_doc.append({
                "record": rid, "n_frags": len(ids), "doc_words": total,
                "floor_words": floor, "recovered_words": max(best_words[rid], floor),
                "longest_run_frags": max(best_frag[rid], 1),
                "join_recall": joins.get(rid, 0) / (len(ids) - 1) if len(ids) > 1 else None,
            })
    return per_doc


def main():
    out = {}
    print(f"{'arm':10s} {'docs':>5s} {'frags/doc':>9s} {'doc wds':>8s} "
          f"{'floor':>7s} {'recov':>7s} {'lift':>6s} {'recov%':>7s} {'floor%':>7s} {'join rec':>9s}")
    for label, cell, pred in ARMS:
        pd = arm_stats(cell, pred)
        dw = st.fmean([d["doc_words"] for d in pd])
        fl = st.fmean([d["floor_words"] for d in pd])
        rc = st.fmean([d["recovered_words"] for d in pd])
        jr = [d["join_recall"] for d in pd if d["join_recall"] is not None]
        row = {"n_docs": len(pd),
               "frags_per_doc": st.fmean([d["n_frags"] for d in pd]),
               "doc_words": dw, "floor_words": fl, "recovered_words": rc,
               "lift_words": rc - fl,
               "recovered_pct": 100 * rc / dw, "floor_pct": 100 * fl / dw,
               "longest_run_frags": st.fmean([d["longest_run_frags"] for d in pd]),
               "join_recall": st.fmean(jr) if jr else None}
        out[label] = row
        print(f"{label:10s} {len(pd):5d} {row['frags_per_doc']:9.2f} {dw:8.1f} "
              f"{fl:7.2f} {rc:7.2f} {rc-fl:6.2f} {row['recovered_pct']:6.1f}% "
              f"{row['floor_pct']:6.1f}% {row['join_recall']:9.4f}")

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(out, open(OUT, "w", encoding="utf-8"), indent=1)
    print(f"\nwrote {OUT}")
    print("\nfloor  = longest single fragment, i.e. contiguous original text leaked by the CUT alone")
    print("recov  = longest stretch the attacker holds consecutively AND in true order")
    print("lift   = recov - floor, the attacker's own contribution")


if __name__ == "__main__":
    main()
