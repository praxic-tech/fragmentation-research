#!/usr/bin/env python3
"""
cost_grid.py — projected LLM cost of the full (cut strategy x granularity) grid.

NO API CALLS. Fragment counts are MEASURED from prose_v4 (spaCy for clauses,
tokenizer for windows); costs come from the calibrated model.

Why fragment count is the cost driver
-------------------------------------
Input text is ~constant across the grid — every cell cuts the SAME corpus, just
at different boundaries. What changes is the number of fragments, which drives:
  * output tokens (ordering: ~15/frag, linkage: ~3/frag before calibration)
  * per-fragment label overhead in the prompt ("item_1234: " ~ 11 chars)
Cut STRATEGY barely moves fragment count at a fixed granularity; GRANULARITY
moves it a lot. So the grid's cost is essentially 4 strategies x 3 sizes.

Calibration (measured, see calibration_small.json / reasoning_sweep.json):
  chars/token on clinical text  1.541x the naive /4 estimate
  ordering output              1.976x the 15/frag estimate
  linkage output              30.861x the 3/frag estimate  <-- thinking tokens
  linkage output, thinking off  2.082x                     <-- the cheap variant

Usage:
    python cost_grid.py --bound 71
    python cost_grid.py --bound 71 --window-k 20
"""

import argparse
import json
import math
import statistics as st
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
IN_PER_M, OUT_PER_M = 2.0, 10.0
CAL_IN, CAL_O_OUT = 1.541, 1.976
CAL_L_OUT_THINK, CAL_L_OUT_NOTHINK = 30.861, 2.082
POOL_RECORDS = 100
LABEL_CHARS = 11          # "item_1234: "

# The grid. skip = degenerate (subject-verb at token-window ~= random).
STRATEGIES = ["random", "semantic", "coherence-sever", "subject-verb"]
GRANS = ["sentence", "clause", "token-window"]
SKIP = {("subject-verb", "token-window")}
LLM_CUT = "llm-cut"       # 1 cell, model picks its own granularity


def measure(data, bound, window_k):
    """Measure per-granularity fragment counts on the real corpus."""
    d = Path(data)
    frs = [json.loads(l) for l in (d / "prose_fragments.jsonl").open(encoding="utf-8") if l.strip()]
    by = defaultdict(list)
    for f in frs:
        by[f["record_id"]].append(f)

    # Apply the upper bound the same way the corpus would be trimmed.
    docs = {r: v[:bound] for r, v in by.items()}
    n_docs = len(docs)
    sent_counts = {r: len(v) for r, v in docs.items()}
    chars = {r: sum(len(f["text"]) for f in v) for r, v in docs.items()}
    texts = {r: " ".join(f["text"] for f in v) for r, v in docs.items()}

    total_sent = sum(sent_counts.values())
    total_chars = sum(chars.values())

    # ── clauses: spaCy dependency parse, on a sample for speed ──────────────
    import spacy
    nlp = spacy.load("en_core_web_sm", exclude=["ner", "lemmatizer", "textcat"])
    CLAUSE_DEPS = {"advcl", "ccomp", "xcomp", "relcl", "acl", "conj"}
    sample_recs = sorted(docs)[:60]                      # 60 docs is plenty for a ratio
    sample_sents = [f["text"] for r in sample_recs for f in docs[r]]
    n_clause, n_seen = 0, 0
    for doc in nlp.pipe(sample_sents, batch_size=64):
        n_seen += 1
        extra = sum(1 for t in doc if t.dep_ in CLAUSE_DEPS and t.pos_ in ("VERB", "AUX"))
        n_clause += 1 + extra
    clause_ratio = n_clause / n_seen if n_seen else 1.0

    # ── token windows: total word tokens / k ────────────────────────────────
    total_tokens = sum(len(t.split()) for t in texts.values())

    return {
        "n_docs": n_docs,
        "total_chars": total_chars,
        "total_sentences": total_sent,
        "clause_ratio": clause_ratio,
        "total_clauses": round(total_sent * clause_ratio),
        "total_tokens": total_tokens,
        "total_windows": math.ceil(total_tokens / window_k),
        "sample_sentences": n_seen,
        "docs": docs, "chars": chars, "sent_counts": sent_counts,
    }


def cell_cost(n_docs, total_chars, n_frags, l_out_factor):
    """Cost of one full run (ordering + linkage) for a given fragment count."""
    # Ordering: one call per document. Input = doc text + per-fragment labels.
    o_in = (total_chars + n_frags * LABEL_CHARS) / 4 + 150 * n_docs
    o_out = n_frags * 15
    # Linkage: pools of POOL_RECORDS documents.
    n_pools = math.ceil(n_docs / POOL_RECORDS)
    l_in = (total_chars + n_frags * LABEL_CHARS) / 4 + 200 * n_pools
    l_out = n_frags * 3
    o_in, o_out = o_in * CAL_IN, o_out * CAL_O_OUT
    l_in, l_out = l_in * CAL_IN, l_out * l_out_factor
    usd = lambda i, o: i / 1e6 * IN_PER_M + o / 1e6 * OUT_PER_M
    return {"o": usd(o_in, o_out), "l": usd(l_in, l_out),
            "total": usd(o_in, o_out) + usd(l_in, l_out), "frags": n_frags}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(Path(__file__).resolve().parent.parent / "data" / "prose"))
    ap.add_argument("--bound", type=int, default=71, help="fragments/doc cap (95th pct)")
    ap.add_argument("--window-k", type=int, default=15, help="tokens per window fragment")
    ap.add_argument("--repeat-cell", default="semantic/sentence")
    ap.add_argument("--repeats", type=int, default=5)
    args = ap.parse_args()

    m = measure(args.data, args.bound, args.window_k)
    print("=" * 84)
    print(f" MEASURED FRAGMENT COUNTS — prose_v4, bound={args.bound}, k={args.window_k}")
    print("=" * 84)
    print(f"  documents            : {m['n_docs']}")
    print(f"  total chars          : {m['total_chars']:,}")
    print(f"  sentence fragments   : {m['total_sentences']:,}")
    print(f"  clause  fragments    : {m['total_clauses']:,}  "
          f"({m['clause_ratio']:.2f} clauses/sentence, measured on {m['sample_sentences']:,} sentences)")
    print(f"  token-window frags   : {m['total_windows']:,}  "
          f"({m['total_tokens']:,} tokens / k={args.window_k})")

    frags_by_gran = {
        "sentence": m["total_sentences"],
        "clause": m["total_clauses"],
        "token-window": m["total_windows"],
    }

    for label, factor in (("THINKING ON (measured 30.86x)", CAL_L_OUT_THINK),
                          ("THINKING OFF (measured 2.08x)", CAL_L_OUT_NOTHINK)):
        print()
        print("=" * 84)
        print(f" GRID COST — {label}")
        print("=" * 84)
        print(f"{'':18s} " + "".join(f"{g:>20s}" for g in GRANS))
        print(f"{'':18s} " + "".join(f"{'(' + f'{frags_by_gran[g]:,}' + ' frags)':>20s}" for g in GRANS))
        print("-" * 84)
        cells = {}
        for s in STRATEGIES:
            row = f"{s:18s} "
            for g in GRANS:
                if (s, g) in SKIP:
                    row += f"{'— skip —':>20s}"
                    continue
                c = cell_cost(m["n_docs"], m["total_chars"], frags_by_gran[g], factor)
                cells[(s, g)] = c
                cell_str = "$%.2f" % c["total"]
                row += "%20s" % cell_str
            print(row)
        # llm-cut: model picks granularity; price it at the clause midpoint
        c_llm = cell_cost(m["n_docs"], m["total_chars"], frags_by_gran["clause"], factor)
        cells[(LLM_CUT, "self")] = c_llm
        llm_str = "$%.2f" % c_llm["total"]
        print("%-18s %20s   (model picks granularity; priced at the clause midpoint)"
              % (LLM_CUT, llm_str))
        print("-" * 84)

        rs, rg = args.repeat_cell.split("/")
        repeat = cells[(rs, rg)]["total"]
        singles = sum(v["total"] for k, v in cells.items() if k != (rs, rg))
        n_cells = len(cells)
        grand = repeat * args.repeats + singles
        print(f"  cells: {n_cells}  ({rs}/{rg} x{args.repeats} + {n_cells-1} x1 = "
              f"{args.repeats + n_cells - 1} runs)")
        print(f"  {rs}/{rg} x{args.repeats:<2d}       ${repeat*args.repeats:9.2f}")
        print(f"  other {n_cells-1} cells x1  ${singles:9.2f}")
        print(f"  GRAND TOTAL         ${grand:9.2f}")


if __name__ == "__main__":
    main()
