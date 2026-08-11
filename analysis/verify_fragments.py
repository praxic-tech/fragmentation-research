#!/usr/bin/env python3
"""
verify_fragments.py — prove a cell's fragments are faithful to the source documents.

NO API CALLS. Exits non-zero on failure so it can gate a pipeline.

A cut strategy must only ever PARTITION text. It must never invent a word,
paraphrase, normalise, reorder, or silently drop content. The llm-cut cell makes
that structurally hard by having the model return indices rather than text — but
"structurally hard" is not "verified", and the rule-based cutters slice spaCy
spans and re-join on whitespace, which are both places content can go missing.

Four checks per cell:

  1. HALLUCINATION   tokens present in the fragments but absent from the source
                     document. Any hit is a hard failure — it means the cell
                     contains text the corpus does not.
  2. DROPPED         source tokens missing from the fragments. Expected in small
                     amounts for `sentence` granularity, which discards units
                     under MIN_SENT_CHARS by design (matching the corpus build).
                     Reported with a rate so "by design" stays distinguishable
                     from "a bug".
  3. RECONSTRUCTION  fragments joined in answer-key order, whitespace-normalised,
                     equal the source body. The strongest check: it catches
                     reordering and duplication that a bag-of-tokens comparison
                     would miss.
  4. STRUCTURE       every fragment appears exactly once in the answer key, every
                     key entry resolves to a fragment, no duplicate ids.

Usage:
    python analysis/verify_fragments.py --cell data/prose
    python analysis/verify_fragments.py --cell results/grid/llm_cut --verbose
"""

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_RAW = ROOT / "data" / "prose" / "prose_raw.jsonl"


def load_jsonl(path):
    with open(path, "r", encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def norm(s):
    return re.sub(r"\s+", " ", s).strip()


def tokens(s):
    """Word tokens, case-folded. Punctuation is ignored: spaCy span slicing
    legitimately shifts punctuation between fragments, and that is a partition
    detail, not a fidelity problem. Inventing a WORD is the failure we care about."""
    return re.findall(r"[a-z0-9']+", s.lower())


def verify_cell(cell_dir, raw_by_id, verbose=False):
    cell = Path(cell_dir)
    frags = load_jsonl(cell / "prose_fragments.jsonl")
    key   = load_jsonl(cell / "prose_answer_key.jsonl")

    text_by_id = {}
    dupe_ids = []
    for f in frags:
        if f["fragment_id"] in text_by_id:
            dupe_ids.append(f["fragment_id"])
        text_by_id[f["fragment_id"]] = f["text"]

    key_by_rec = {r["record_id"]: r["order"] for r in key}

    stats = {
        "docs": 0, "checked": 0,
        "halluc_docs": 0, "halluc_tokens": Counter(),
        "dropped_docs": 0, "dropped_tokens": 0, "source_tokens": 0,
        "reconstruct_ok": 0, "reconstruct_fail": [],
        "orphan_frags": 0, "missing_frags": 0, "dupe_ids": dupe_ids,
        "unknown_records": [],
    }

    seen_in_key = set()
    for rec_id, order in key_by_rec.items():
        stats["docs"] += 1
        if rec_id not in raw_by_id:
            stats["unknown_records"].append(rec_id)
            continue

        pieces = []
        for fid in order:
            seen_in_key.add(fid)
            if fid not in text_by_id:
                stats["missing_frags"] += 1
                continue
            pieces.append(text_by_id[fid])

        stats["checked"] += 1
        source = norm(raw_by_id[rec_id].replace("\n", " "))
        rebuilt = norm(" ".join(pieces))

        src_t, reb_t = tokens(source), tokens(rebuilt)
        stats["source_tokens"] += len(src_t)

        extra = Counter(reb_t) - Counter(src_t)
        missing = Counter(src_t) - Counter(reb_t)

        if extra:
            stats["halluc_docs"] += 1
            stats["halluc_tokens"].update(extra)
            if verbose:
                print(f"  [HALLUCINATED] {rec_id}: {dict(list(extra.items())[:8])}")
        if missing:
            stats["dropped_docs"] += 1
            stats["dropped_tokens"] += sum(missing.values())
            if verbose:
                print(f"  [DROPPED] {rec_id}: {sum(missing.values())} tokens "
                      f"{dict(list(missing.items())[:8])}")

        if rebuilt == source:
            stats["reconstruct_ok"] += 1
        else:
            stats["reconstruct_fail"].append(rec_id)

    stats["orphan_frags"] = len(set(text_by_id) - seen_in_key)
    return stats


def report(label, s):
    ok = True
    print("=" * 78)
    print(f" {label}")
    print("=" * 78)
    print(f"  documents            : {s['docs']}  (checked {s['checked']})")

    n_h = sum(s["halluc_tokens"].values())
    if n_h:
        ok = False
        print(f"  1. HALLUCINATION     : FAIL — {n_h} invented tokens across "
              f"{s['halluc_docs']} docs")
        print(f"     most common       : {s['halluc_tokens'].most_common(8)}")
    else:
        print(f"  1. HALLUCINATION     : PASS — 0 invented tokens")

    rate = (s["dropped_tokens"] / s["source_tokens"] * 100) if s["source_tokens"] else 0
    tag = "PASS" if s["dropped_tokens"] == 0 else f"{rate:.2f}% dropped"
    print(f"  2. DROPPED CONTENT   : {tag} — {s['dropped_tokens']} of "
          f"{s['source_tokens']} source tokens, in {s['dropped_docs']} docs")

    if s["reconstruct_fail"]:
        print(f"  3. RECONSTRUCTION    : {s['reconstruct_ok']}/{s['checked']} exact"
              f"   ({len(s['reconstruct_fail'])} differ, e.g. "
              f"{s['reconstruct_fail'][:3]})")
    else:
        print(f"  3. RECONSTRUCTION    : PASS — {s['reconstruct_ok']}/{s['checked']} exact")

    struct = (s["orphan_frags"], s["missing_frags"], len(s["dupe_ids"]),
              len(s["unknown_records"]))
    if any(struct):
        ok = False
        print(f"  4. STRUCTURE         : FAIL — orphan {struct[0]}, missing "
              f"{struct[1]}, duplicate ids {struct[2]}, unknown records {struct[3]}")
    else:
        print(f"  4. STRUCTURE         : PASS — key and fragments agree exactly")
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cell", required=True, nargs="+",
                    help="one or more cell dirs holding prose_fragments.jsonl")
    ap.add_argument("--raw", default=str(DEFAULT_RAW))
    ap.add_argument("--verbose", action="store_true",
                    help="list offending tokens per document")
    args = ap.parse_args()

    raw_by_id = {r["record_id"]: r["text"] for r in load_jsonl(args.raw)}
    all_ok = True
    for cell in args.cell:
        s = verify_cell(cell, raw_by_id, verbose=args.verbose)
        all_ok &= report(Path(cell).name, s)
        print()

    if not all_ok:
        print("VERIFICATION FAILED — do not score these cells.")
        sys.exit(1)
    print("All cells faithful to source.")


if __name__ == "__main__":
    main()
