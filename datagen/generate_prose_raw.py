"""
Generate prose_raw.jsonl from an existing prose corpus.

Reads prose_fragments.jsonl and prose_answer_key.jsonl (or an order-schema
answer key), joins each record's fragments in true positional order, and
writes prose_raw.jsonl with one line per record:
    {"record_id": "prose_001", "text": "<full document body>"}

This file is the single input every cut strategy reads from. All cutters
work from the raw body text, not from pre-split sentences, so that
random / token-window / coherence-sever can cut across sentence boundaries.

Usage:
    python generate_prose_raw.py
    python generate_prose_raw.py \\
        --fragments  prose_fragments.jsonl \\
        --answer-key prose_answer_key.jsonl \\
        --out        prose_raw.jsonl
"""

import argparse
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # repo root
PROSE = os.path.join(ROOT, "data", "prose")

DEFAULT_FRAGMENTS  = os.path.join(PROSE, "prose_fragments.jsonl")
DEFAULT_ANSWER_KEY = os.path.join(PROSE, "prose_answer_key.jsonl")
DEFAULT_OUT        = os.path.join(PROSE, "prose_raw.jsonl")


def load_jsonl(path):
    with open(path, "r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def build_prose_raw(fragments_path, answer_key_path, out_path):
    # index fragment text by id
    frag_text = {}
    for row in load_jsonl(fragments_path):
        frag_text[row["fragment_id"]] = row["text"]

    records = []
    key_rows = load_jsonl(answer_key_path)

    # handle both answer key schemas:
    #   order schema (prose):      {"record_id": ..., "order": [...]}
    #   position schema (identifier): {"fragment_id": ..., "record_id": ..., "position": ...}
    if "order" in key_rows[0]:
        for row in key_rows:
            text = " ".join(
                frag_text[fid] for fid in row["order"] if fid in frag_text
            )
            records.append({"record_id": row["record_id"], "text": text})
    else:
        by_record = {}
        for row in key_rows:
            by_record.setdefault(row["record_id"], []).append(row)
        for record_id, frags in sorted(by_record.items()):
            ordered = sorted(frags, key=lambda r: r["position"])
            text = " ".join(
                frag_text[r["fragment_id"]] for r in ordered
                if r["fragment_id"] in frag_text
            )
            records.append({"record_id": record_id, "text": text})

    with open(out_path, "w", encoding="utf-8") as handle:
        for rec in records:
            handle.write(json.dumps(rec) + "\n")

    token_counts = [len(r["text"].split()) for r in records]
    print(f"wrote {len(records)} records -> {out_path}")
    print(f"tokens per doc: min={min(token_counts)}  "
          f"max={max(token_counts)}  "
          f"mean={sum(token_counts)/len(token_counts):.0f}")
    return records


def parse_args():
    parser = argparse.ArgumentParser(
        description="Build prose_raw.jsonl from fragments + answer key."
    )
    parser.add_argument("--fragments",  default=DEFAULT_FRAGMENTS)
    parser.add_argument("--answer-key", default=DEFAULT_ANSWER_KEY)
    parser.add_argument("--out",        default=DEFAULT_OUT)
    return parser.parse_args()


def main():
    args = parse_args()
    # CLI paths are taken as given (relative to the current working directory);
    # only the defaults are anchored to the repo root.
    build_prose_raw(
        fragments_path  = args.fragments,
        answer_key_path = args.answer_key,
        out_path        = args.out,
    )


if __name__ == "__main__":
    main()
