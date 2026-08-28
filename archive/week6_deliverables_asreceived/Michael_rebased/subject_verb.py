"""
subject_verb.py — the "subject-verb" strategy for the fragmentation grid.

    cut(text, granularity, window_size=None) -> list[str]

Rule (exact, per spec — do not broaden): within each granularity unit
(sentence or clause — token-window is skipped, see below), scan tokens for
dep_ == "nsubj" (nsubj only — nsubjpass does NOT count here, unlike an
earlier draft of this strategy that included it). On the first nsubj found,
cut the unit in two, right before token.head — the verb it attaches to. That
produces (subject phrase) | (verb onward) as two fragments for that unit.

If no nsubj is found in a unit: don't cut it, full stop. The unit is emitted
as a single whole fragment. It is NOT replaced by cutting at the unit's own
sentence/clause boundary instead — that fallback would make a unit look like
it got a "subject-verb cut" when it didn't, which hides how often this
strategy actually fires. The whole point of --report-boundaries below is to
surface that number honestly.

Fire rate = (units where a subject-verb cut actually happened) / (total
units scanned). Below ~20%, the cell has effectively collapsed onto
semantic (most units pass through unmodified) and isn't worth scoring —
--report-boundaries prints this and warns explicitly when it's low.

token-window is not implemented here — subject-verb boundaries aren't
meaningfully defined over an arbitrary fixed-size token span, and the grid
marks this cell "skip" for exactly that reason. Calling cut() with
granularity="token-window" raises rather than silently degrading.
"""

import argparse
import json
import os

from grid_common import get_nlp, split_sentences, split_clauses, load_jsonl, write_jsonl_pairs

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(BASE_DIR))
DEFAULT_RAW = os.path.join(ROOT, "data", "prose", "prose_raw.jsonl")


def _cut_unit(unit_text):
    """Returns (fragments, fired) where fragments is 1 or 2 strings and
    fired is True only if an nsubj -> head cut actually happened."""
    doc = get_nlp()(unit_text)
    for tok in doc:
        if tok.dep_ == "nsubj":
            head = tok.head
            if head.i > 0:  # cut point must be a real interior boundary
                pre = doc[:head.i].text.strip()
                post = doc[head.i:].text.strip()
                if pre and post:
                    return [pre, post], True
    return [unit_text.strip()], False


def cut(text, granularity="sentence", window_size=None):
    if granularity == "token-window":
        raise ValueError(
            "subject-verb x token-window is 'skip' in the grid — not implemented by design"
        )
    if granularity not in ("sentence", "clause"):
        raise ValueError(f"unknown granularity for subject-verb: {granularity!r}")

    units = split_sentences(text) if granularity == "sentence" else split_clauses(text)
    fragments, fired_count = [], 0
    for unit in units:
        pieces, fired = _cut_unit(unit)
        fragments.extend(pieces)
        fired_count += int(fired)

    return fragments, fired_count, len(units)


def cut_corpus(raw_path, out_dir, granularity="sentence", report_boundaries=False):
    records = load_jsonl(raw_path)

    fire_stats = {"fired": 0, "total_units": 0}

    def records_fn(record_id, text):
        fragments, fired, total = cut(text, granularity=granularity)
        fire_stats["fired"] += fired
        fire_stats["total_units"] += total
        return fragments

    frag_path, key_path, frag_counts = write_jsonl_pairs(
        records_fn, records, out_dir, cell_name=f"subject-verb_{granularity}"
    )

    print(f"[subject-verb x {granularity}]  {len(records)} records -> {sum(frag_counts)} fragments  "
          f"(min={min(frag_counts)}, max={max(frag_counts)}, mean={sum(frag_counts)/len(frag_counts):.1f})")
    print(f"  wrote: {frag_path}")
    print(f"  wrote: {key_path}")

    fire_rate = (fire_stats["fired"] / fire_stats["total_units"]) if fire_stats["total_units"] else 0.0
    if report_boundaries:
        print(f"  [report] fire rate: {fire_stats['fired']}/{fire_stats['total_units']} "
              f"units cut ({fire_rate:.1%})")
        if fire_rate < 0.20:
            print(f"  [report] WARNING: fire rate {fire_rate:.1%} is under ~20% — this cell has "
                  f"likely collapsed onto semantic (most units pass through uncut). Consider not "
                  f"paying for scoring on this cell until that's addressed.")
    return fire_rate


def parse_args():
    parser = argparse.ArgumentParser(description="Cut a prose corpus with the subject-verb strategy.")
    parser.add_argument("--raw", default=DEFAULT_RAW)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--granularity", default="sentence", choices=["sentence", "clause"])
    parser.add_argument("--report-boundaries", action="store_true")
    return parser.parse_args()


def main():
    args = parse_args()
    cut_corpus(
        args.raw,
        args.out_dir,
        granularity=args.granularity,
        report_boundaries=args.report_boundaries,
    )


if __name__ == "__main__":
    main()
