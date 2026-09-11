"""
build_grid_corpus.py — the frozen, length-capped corpus every grid cell cuts.

Writes data/grid_corpus/prose_raw.jsonl: the 180 documents named by
data/pools/ordering_grid.json, each truncated to the first N sentences, where N
is the cap that makes the REFERENCE cell (semantic x sentence) yield at most 30
fragments.

WHY THE CAP IS ON THE SOURCE AND NOT ON EACH CUTTER'S OUTPUT
------------------------------------------------------------
"180 documents capped at 30 fragments" has two readings and only one of them
leaves an experiment behind.

Capping each CUTTER'S OUTPUT at 30 fragments, measured on this selection:

    sentence      mean 24.8 frags/doc      0 of 180 docs pinned at the cap
    clause        mean 27.6 frags/doc    115 of 180 docs pinned at the cap
    token-window  mean 28.9 frags/doc    147 of 180 docs pinned at the cap

Granularity is the independent variable of the entire ordering grid. Capping
outputs collapses it: the three granularities become 24.8 / 27.6 / 28.9
fragments per document, and 64% of clause documents and 82% of token-window
documents sit at exactly 30 because the cap, not the cutter, decided. You would
pay for twelve cells and measure the cap.

Capping the SOURCE — truncate the document, then let each cutter cut it
naturally — gives 24.8 / 32.4 / 41.4 and the axis survives. analysis/
cost_model_v2.py already prices this reading (`min(nfrag[d], CAP) * mult`), so
it is also the one the budget was built on.

WHY THIS IS A FILE AND NOT A FLAG
---------------------------------
Every cell must cut the identical text. A cap applied independently inside each
cutter is a cap that can drift between cutters, and the failure is silent: the
cells still produce numbers, they are just no longer comparable. Writing the
capped corpus once, hashing it, and pointing every cell at the same file makes
that impossible rather than merely unlikely.

It also keeps verification honest. analysis/verify_fragments.py reconstructs a
cell against its source; a cell cut from truncated text and checked against the
FULL document would fail reconstruction by construction, and we would either
have to weaken the check or learn to ignore it. Both are worse than truncating
the source. Cells cut from this file reconstruct it exactly.

    python datagen/build_grid_corpus.py
    python datagen/build_grid_corpus.py --verify

Then every grid cell runs with --raw data/grid_corpus/prose_raw.jsonl.
"""

import argparse
import hashlib
import json
import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(BASE_DIR)
sys.path.insert(0, BASE_DIR)

from prose_cutter import split_sentences, cut          # noqa: E402

DEFAULT_RAW = os.path.join(ROOT, "data", "prose", "prose_raw.jsonl")
DEFAULT_SELECTION = os.path.join(ROOT, "data", "pools", "ordering_grid.json")
DEFAULT_OUT = os.path.join(ROOT, "data", "grid_corpus")


def load_jsonl(path):
    with open(path, "r", encoding="utf-8") as fh:
        return [json.loads(l) for l in fh if l.strip()]


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def truncate(text, cap):
    """First `cap` sentences of text, as the shared splitter sees them.

    Returns (truncated_text, n_sentences_kept, n_sentences_total). Uses the same
    splitter every cutter imports, so the sentence the cap falls on is the same
    sentence for all of them.
    """
    sents = split_sentences(text)
    kept = sents[:cap]
    return " ".join(kept), len(kept), len(sents)


def build(raw_path, selection_path, out_dir, force):
    out_raw = os.path.join(out_dir, "prose_raw.jsonl")
    manifest_path = os.path.join(out_dir, "manifest.json")
    if os.path.exists(manifest_path) and not force:
        raise SystemExit(
            f"refusing to overwrite {manifest_path}\n"
            "  Every grid cell cuts this exact file. Rebuilding it after any cell\n"
            "  has run makes those cells incomparable to the ones that follow.\n"
            "  Pass --force only if nothing has been cut against it yet."
        )

    selection = json.load(open(selection_path, encoding="utf-8"))
    cap = selection["fragment_cap"]
    wanted = [d["record_id"] for d in selection["documents"]]

    by_id = {r["record_id"]: r for r in load_jsonl(raw_path)}
    missing = [r for r in wanted if r not in by_id]
    if missing:
        raise SystemExit(f"{len(missing)} selected ids are not in {raw_path}: {missing[:3]}")

    os.makedirs(out_dir, exist_ok=True)
    rows, truncated, kept_total, full_total = [], 0, 0, 0
    adjusted = []
    for rid in wanted:
        full = by_id[rid]["text"]
        text, kept, total = truncate(full, cap)
        # Sentence splitting is context-sensitive: re-splitting the JOINED first
        # `cap` sentences can give cap + 1 (measured: prose_0305, 30 -> 31), so a
        # single truncation does not guarantee the cap it promises. Drop one
        # sentence at a time until the reference cut respects it, and record it.
        while kept > 1 and len(cut(text, strategy="semantic",
                                   granularity="sentence")) > cap:
            text, kept, total = truncate(full, kept - 1)
        if kept < min(cap, total):
            adjusted.append({"record_id": rid, "sentences_kept": kept,
                             "sentences_total": total})
        rows.append({"record_id": rid, "text": text})
        truncated += int(kept < total)
        kept_total += kept
        full_total += total

    with open(out_raw, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")

    # Confirm the reference cell actually respects the cap on this file before
    # anyone spends money cutting eleven more cells from it.
    ref = [len(cut(r["text"], strategy="semantic", granularity="sentence"))
           for r in rows]
    over = [rid for rid, n in zip(wanted, ref) if n > cap]

    manifest = {
        "source_raw": os.path.relpath(raw_path, ROOT).replace("\\", "/"),
        "source_sha256": sha256(raw_path),
        "selection": os.path.relpath(selection_path, ROOT).replace("\\", "/"),
        "selection_seed": selection.get("seed"),
        "fragment_cap": cap,
        "cap_adjusted": adjusted,
        "cap_applied_to": "source_text",
        "n_documents": len(rows),
        "documents_truncated": truncated,
        "sentences_kept": kept_total,
        "sentences_in_full_documents": full_total,
        "reference_fragments": sum(ref),
        "reference_max_per_doc": max(ref),
        "grid_corpus_sha256": sha256(out_raw),
    }
    json.dump(manifest, open(manifest_path, "w", encoding="utf-8"), indent=2)

    print(f"documents      : {len(rows)}  ({truncated} truncated, "
          f"{len(rows) - truncated} used whole)")
    print(f"sentences      : {kept_total} kept of {full_total} "
          f"({kept_total / full_total:.1%})")
    print(f"reference cell : {sum(ref)} fragments, max {max(ref)}/doc, cap {cap}")
    if over:
        raise SystemExit(f"FAIL: {len(over)} documents still exceed the cap: {over[:3]}")
    print(f"cap respected  : yes, {max(ref)} <= {cap}")
    print(f"\nwrote {out_raw}")
    print(f"      {manifest_path}")
    print("\nrun the grid with:  --raw data/grid_corpus/prose_raw.jsonl")


def verify(out_dir, raw_path, selection_path):
    manifest = json.load(open(os.path.join(out_dir, "manifest.json"), encoding="utf-8"))
    out_raw = os.path.join(out_dir, "prose_raw.jsonl")
    rows = load_jsonl(out_raw)
    problems = []

    if sha256(out_raw) != manifest["grid_corpus_sha256"]:
        problems.append("grid corpus file has changed since it was built")
    if sha256(raw_path) != manifest["source_sha256"]:
        problems.append("data/prose/prose_raw.jsonl has changed since the cap was applied")

    selection = json.load(open(selection_path, encoding="utf-8"))
    wanted = [d["record_id"] for d in selection["documents"]]
    if [r["record_id"] for r in rows] != wanted:
        problems.append("grid corpus documents do not match ordering_grid.json")

    cap = manifest["fragment_cap"]
    ref = [len(cut(r["text"], strategy="semantic", granularity="sentence")) for r in rows]
    if max(ref) > cap:
        problems.append(f"reference cell exceeds the cap: max {max(ref)} > {cap}")

    full = {r["record_id"]: r["text"] for r in load_jsonl(raw_path)}
    not_prefix = [r["record_id"] for r in rows
                  if not full[r["record_id"]].startswith(r["text"].split(" ")[0])]

    print(f"documents      : {len(rows)}")
    print(f"reference cell : {sum(ref)} fragments, max {max(ref)}/doc, cap {cap}")
    hash_ok = sha256(out_raw) == manifest["grid_corpus_sha256"]
    print(f"corpus hash    : {'MATCHES' if hash_ok else 'CHANGED'}")
    if not_prefix:
        problems.append(f"{len(not_prefix)} documents are not prefixes of their source")
    if problems:
        print("\nFAILED:")
        for p in problems:
            print(f"  - {p}")
        raise SystemExit(1)
    print("\nGrid corpus is valid and current.")


def parse_args():
    ap = argparse.ArgumentParser(description="Build the length-capped grid corpus.")
    ap.add_argument("--raw", default=DEFAULT_RAW)
    ap.add_argument("--selection", default=DEFAULT_SELECTION)
    ap.add_argument("--out-dir", default=DEFAULT_OUT)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--verify", action="store_true")
    return ap.parse_args()


def main():
    a = parse_args()
    if a.verify:
        verify(a.out_dir, a.raw, a.selection)
    else:
        build(a.raw, a.selection, a.out_dir, a.force)


if __name__ == "__main__":
    main()
