"""
random_cut.py — the "random" strategy for the fragmentation grid.

    cut(text, granularity, window_size=DEFAULT_WINDOW, seed=None, target_fragments=None) -> list[str]

Design constraint (critical, not optional): fragment COUNT is controlled to
match the reference cell — semantic's natural unit count at the same
granularity — by default. If random x sentence produced a different number
of fragments per doc than semantic x sentence, any scoring gap between the
two could just be fragment count doing the work, not the strategy. So:

    target_fragments defaults to len(units_for_granularity(text, granularity))
    (grid_common.reference_fragment_count) — the same count semantic gets —
    and random_cut hits that count exactly (clamped only if the doc doesn't
    have enough token positions to support it).

Cut MECHANISM is deliberately not locked to sentence/clause boundaries: it
picks target_fragments-1 random token-boundary positions across the whole
document (spaCy tokenization, so positions line up with the other cutters'
notion of a token). That's the actual controlled comparison this strategy
is for — same fragment count as semantic, but arbitrary vs. structural cut
placement.

Seeding: every call takes an explicit `seed` and builds a local
`random.Random(seed)` instance — the global `random` module is never
touched. The harness seeds this per Monte Carlo trial; reusing the global
module would mean the harness's seeding doesn't actually control this
strategy's randomness. --seed on the CLI seeds a per-document counter
(base_seed + doc_index) for a reproducible standalone run; the harness
should call cut() directly with its own trial seeds for real Monte Carlo use.

Cut positions are plain whitespace-delimited words (text.split()), the same
notion of "token" Arafat's own token-window splitter uses — not spaCy
sub-word tokens. This matters: spaCy splits hyphenated compounds like
"58-year-old" into sub-tokens with no whitespace between them ("58", "-",
"year", "-", "old"), and a cut landing inside that cluster broke the
single-space reconstruction contract (rejoining produced "58- year-old",
not the original). Whitespace-word boundaries can't have that problem —
there's always a real space at every candidate cut point, so " ".join of
the resulting fragments reproduces the original exactly (mod any
already-collapsed internal whitespace, which this corpus doesn't have).
"""

import argparse
import json
import os
import random

from grid_common import (DEFAULT_WINDOW, reference_fragment_count,
                         load_jsonl, write_jsonl_pairs)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(BASE_DIR))
DEFAULT_RAW = os.path.join(ROOT, "data", "prose", "prose_raw.jsonl")


def cut(text, granularity="sentence", window_size=DEFAULT_WINDOW, seed=None, target_fragments=None):
    if target_fragments is None:
        target_fragments = reference_fragment_count(text, granularity, window_size=window_size)

    words = text.split()
    n = len(words)

    if n == 0:
        return []
    if target_fragments <= 1 or n < 2:
        return [text.strip()]

    # can't have more fragments than internal word boundaries allow
    target_fragments = min(target_fragments, n)

    rng = random.Random(seed)
    cut_positions = sorted(rng.sample(range(1, n), target_fragments - 1))

    edges = [0] + cut_positions + [n]
    fragments = []
    for start, end in zip(edges, edges[1:]):
        chunk = " ".join(words[start:end]).strip()
        if chunk:
            fragments.append(chunk)
    return fragments


def cut_corpus(raw_path, out_dir, granularity="sentence", window_size=DEFAULT_WINDOW, seed=None,
               report_boundaries=False):
    records = load_jsonl(raw_path)

    def records_fn(record_id, text, _counter=[0]):
        doc_seed = None if seed is None else seed + _counter[0]
        _counter[0] += 1
        return cut(text, granularity=granularity, window_size=window_size,
                   seed=doc_seed, target_fragments=None)

    frag_path, key_path, frag_counts = write_jsonl_pairs(
        records_fn, records, out_dir, cell_name=f"random_{granularity}"
    )

    ref_counts = [reference_fragment_count(r["text"], granularity, window_size) for r in records]
    matched = sum(1 for a, b in zip(frag_counts, ref_counts) if a == b)

    print(f"[random x {granularity}]  {len(records)} records -> {sum(frag_counts)} fragments  "
          f"(min={min(frag_counts)}, max={max(frag_counts)}, mean={sum(frag_counts)/len(frag_counts):.1f})")
    print(f"  wrote: {frag_path}")
    print(f"  wrote: {key_path}")

    if report_boundaries:
        rate = matched / len(records) if records else 0.0
        print(f"  [report] fragment count matched reference (semantic) exactly on "
              f"{matched}/{len(records)} docs ({rate:.0%})")
        if rate < 1.0:
            mismatches = [(r["record_id"], a, b) for r, a, b in
                          zip(records, frag_counts, ref_counts) if a != b]
            print(f"  [report] mismatches (doc, achieved, reference): {mismatches[:5]}"
                  f"{' ...' if len(mismatches) > 5 else ''}")
            print("  [report] mismatches only happen when the doc doesn't have enough "
                  "token positions for the reference count — check these aren't silently "
                  "common before trusting a same-count comparison against semantic.")


def parse_args():
    parser = argparse.ArgumentParser(description="Cut a prose corpus with the random strategy.")
    parser.add_argument("--raw", default=DEFAULT_RAW)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--granularity", default="sentence",
                        choices=["sentence", "clause", "token-window"])
    parser.add_argument("--window-size", type=int, default=DEFAULT_WINDOW)
    parser.add_argument("--seed", type=int, default=None,
                        help="base seed; per-doc seed = base + doc index (standalone CLI runs only — "
                             "the harness should seed cut() directly per Monte Carlo trial)")
    parser.add_argument("--report-boundaries", action="store_true",
                        help="report how often the achieved fragment count matched the semantic reference")
    return parser.parse_args()


def main():
    args = parse_args()
    cut_corpus(
        args.raw,
        args.out_dir,
        granularity=args.granularity,
        window_size=args.window_size,
        seed=args.seed,
        report_boundaries=args.report_boundaries,
    )


if __name__ == "__main__":
    main()
