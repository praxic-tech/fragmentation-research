"""
merge_corpus.py — merge new document batches into prose_raw.jsonl, scaling the
corpus toward the 300-500 doc target.

prose_raw.jsonl is the single source every cutter reads from ({"record_id",
"text"} per doc, full untouched body). This script is the on-ramp for adding
new documents to it in batches, since 300-500 docs will get authored/collected
incrementally rather than all at once.

Accepts new batches as either:
  - .jsonl, one doc per line, {"text": "..."} (record_id is reassigned) or
    {"record_id": "...", "text": "..."} (record_id ignored, reassigned anyway
    so IDs stay contiguous and collision-free across batches)
  - .txt, documents separated by one or more blank lines

Does, in order:
  1. loads the existing corpus (if any) to continue the record_id sequence
     and dedupe against
  2. loads every new batch file, normalizes whitespace
  3. drops exact-duplicate text (case-insensitive, whitespace-normalized) —
     both against the existing corpus and within/across the new batches
  4. drops documents under --min-tokens (default 15) — too short to
     fragment meaningfully at clause/token-window granularity
  5. assigns sequential record_ids continuing from the existing max
  6. writes the merged corpus and prints a stats report

Usage:
    python merge_corpus.py --existing prose_raw.jsonl \\
        --batch new_docs_batch1.jsonl new_docs_batch2.txt \\
        --out prose_raw.jsonl

    # dry run — report what would happen without writing
    python merge_corpus.py --existing prose_raw.jsonl \\
        --batch new_docs_batch1.jsonl --dry-run
"""

import argparse
import json
import os
import re


def load_existing(path):
    if not path or not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def load_batch_jsonl(path):
    docs = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            row = json.loads(line)
            text = row.get("text", "").strip()
            if text:
                docs.append(text)
    return docs


def load_batch_txt(path):
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    chunks = re.split(r"\n\s*\n+", content.strip())
    return [c.strip() for c in chunks if c.strip()]


def load_batch(path):
    if path.endswith(".jsonl"):
        return load_batch_jsonl(path)
    elif path.endswith(".txt"):
        return load_batch_txt(path)
    else:
        raise ValueError(f"unsupported batch file type: {path} (expected .jsonl or .txt)")


def normalize_for_dedupe(text):
    return re.sub(r"\s+", " ", text.strip().lower())


def next_record_id(existing_ids, prefix="prose"):
    nums = []
    for rid in existing_ids:
        m = re.match(rf"{prefix}_(\d+)$", rid)
        if m:
            nums.append(int(m.group(1)))
    return (max(nums) + 1) if nums else 1


def merge(existing_path, batch_paths, out_path, min_tokens=15, id_prefix="prose", dry_run=False):
    existing = load_existing(existing_path)
    seen = {normalize_for_dedupe(r["text"]) for r in existing}
    next_id = next_record_id([r["record_id"] for r in existing], prefix=id_prefix)

    added, dup_skipped, short_skipped = [], 0, 0

    for batch_path in batch_paths:
        for text in load_batch(batch_path):
            key = normalize_for_dedupe(text)
            if key in seen:
                dup_skipped += 1
                continue
            if len(text.split()) < min_tokens:
                short_skipped += 1
                continue
            seen.add(key)
            added.append(text)

    merged = list(existing)
    for text in added:
        merged.append({"record_id": f"{id_prefix}_{next_id:03d}", "text": text})
        next_id += 1

    token_counts = [len(r["text"].split()) for r in merged]
    print(f"existing docs:      {len(existing)}")
    print(f"new docs added:     {len(added)}")
    print(f"duplicates skipped: {dup_skipped}")
    print(f"too-short skipped:  {short_skipped} (< {min_tokens} tokens)")
    print(f"merged total:       {len(merged)}")
    if token_counts:
        print(f"tokens/doc:         min={min(token_counts)}  max={max(token_counts)}  "
              f"mean={sum(token_counts)/len(token_counts):.0f}")

    if dry_run:
        print("[dry run — nothing written]")
        return merged

    with open(out_path, "w", encoding="utf-8") as f:
        for rec in merged:
            f.write(json.dumps(rec) + "\n")
    print(f"wrote: {out_path}")
    return merged


def parse_args():
    parser = argparse.ArgumentParser(description="Merge new document batches into prose_raw.jsonl.")
    parser.add_argument("--existing", default="prose_raw.jsonl",
                        help="current corpus to extend (skip if it doesn't exist yet)")
    parser.add_argument("--batch", nargs="+", required=True,
                        help="one or more new-doc files (.jsonl or .txt)")
    parser.add_argument("--out", default="prose_raw.jsonl", help="output path")
    parser.add_argument("--min-tokens", type=int, default=15)
    parser.add_argument("--id-prefix", default="prose")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main():
    args = parse_args()
    merge(args.existing, args.batch, args.out,
          min_tokens=args.min_tokens, id_prefix=args.id_prefix, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
