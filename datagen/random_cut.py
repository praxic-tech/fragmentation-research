"""
random_cut.py — the "random" strategy for the fragmentation grid.

    cut(text, granularity, seed=None, target_fragments=None) -> list[str]

Splitters and DEFAULT_WINDOW come from datagen/prose_cutter.py.
reference_fragment_count uses those same splitters so rate matching
is valid — it computes against the same ruler the reference cell uses.

Fragment count defaults to the semantic reference count for the same
granularity and document — controls for fragment count so any scoring
difference reflects strategy, not count.

Cut positions are whitespace word boundaries (text.split()), never spaCy
sub-tokens. spaCy splits "58-year-old" into five tokens with no whitespace
between them; a cut landing inside that cluster breaks the single-space
reconstruction contract ("58- year-old"). Whitespace boundaries can't have
that problem: there's always a real space at every cut point.

Seeding: explicit random.Random(seed) per call, never the global random
module. The harness seeds per Monte Carlo trial; the global module would
leak between calls.
"""

import argparse
import json
import os
import hashlib
import random
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "datagen"))
from prose_cutter import split_sentences, split_clauses, DEFAULT_WINDOW  # noqa: E402

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _reference_count(text, granularity):
    if granularity == "sentence":
        return len(split_sentences(text))
    elif granularity == "clause":
        return len(split_clauses(text))
    elif granularity == "token-window":
        words = text.split()
        return max(1, -(-len(words) // DEFAULT_WINDOW))  # ceiling div
    raise ValueError(f"unknown granularity: {granularity!r}")


def _doc_seed(seed, record_id):
    """Per-document seed, stable across processes -- never Python's hash()."""
    return seed + int(hashlib.sha256(str(record_id).encode("utf-8"))
                      .hexdigest()[:8], 16)


def cut(text, granularity="sentence", seed=None, target_fragments=None):
    if target_fragments is None:
        target_fragments = _reference_count(text, granularity)

    words = text.split()
    n = len(words)
    if n == 0:
        return []
    if target_fragments <= 1 or n < 2:
        return [text.strip()]

    target_fragments = min(target_fragments, n)
    rng = random.Random(seed)
    cut_positions = sorted(rng.sample(range(1, n), target_fragments - 1))

    edges = [0] + cut_positions + [n]
    return [" ".join(words[start:end]) for start, end in zip(edges, edges[1:])]


def cut_corpus(raw_path, out_dir, granularity="sentence", seed=None,
               docs=None, report_boundaries=False, **_):
    """
    docs: optional list of record_ids (pool selection from build_pools.py).
    Outputs prose_fragments.jsonl + prose_answer_key.jsonl.
    """
    os.makedirs(out_dir, exist_ok=True)

    with open(raw_path, "r", encoding="utf-8") as f:
        records = [json.loads(l) for l in f if l.strip()]

    if docs is not None:
        doc_set = set(docs)
        records = [r for r in records if r["record_id"] in doc_set]

    frag_path = os.path.join(out_dir, "prose_fragments.jsonl")
    key_path  = os.path.join(out_dir, "prose_answer_key.jsonl")

    frag_counts, ref_counts = [], []
    with open(frag_path, "w", encoding="utf-8") as ff, \
         open(key_path,  "w", encoding="utf-8") as kf:
        for idx, rec in enumerate(records):
            record_id = rec["record_id"]
            # Seed from the document's IDENTITY, not its position in the file.
            # seed + idx gave a document a different random cut depending on
            # which other documents happened to be in the file being cut, so
            # an 8-document test and the full run cut the same document
            # differently: every prompt differed and no test answer could carry
            # over. A cut is a property of the document, not of its neighbours.
            doc_seed = None if seed is None else _doc_seed(seed, rec["record_id"])
            fragments = cut(rec["text"], granularity=granularity, seed=doc_seed)
            frag_counts.append(len(fragments))
            ref_counts.append(_reference_count(rec["text"], granularity))

            order = []
            for position, text in enumerate(fragments):
                fid = f"{record_id}__random_{granularity}_{position:03d}"
                order.append(fid)
                ff.write(json.dumps({
                    "fragment_id": fid, "record_id": record_id, "text": text
                }) + "\n")
            kf.write(json.dumps({"record_id": record_id, "order": order}) + "\n")

    n_docs  = len(records)
    n_frags = sum(frag_counts)
    matched = sum(1 for a, b in zip(frag_counts, ref_counts) if a == b)

    print(f"[random x {granularity}]  {n_docs} docs -> {n_frags} fragments  "
          f"(min={min(frag_counts)}, max={max(frag_counts)}, "
          f"mean={sum(frag_counts)/n_docs:.1f})")
    print(f"  wrote: {frag_path}")
    print(f"  wrote: {key_path}")

    if report_boundaries:
        rate = matched / n_docs
        print(f"  [rate match] {matched}/{n_docs} docs hit semantic reference count ({rate:.0%})")
        if rate < 1.0:
            misses = [(r["record_id"], a, b) for r, a, b in
                      zip(records, frag_counts, ref_counts) if a != b]
            print(f"  [rate match] mismatches (doc, got, ref): {misses[:5]}")

    return {"n_docs": n_docs, "n_fragments": n_frags}


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", default="prose_raw.jsonl")
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--granularity", default="sentence",
                        choices=["sentence", "clause", "token-window"])
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--report-boundaries", action="store_true")
    return parser.parse_args()


def main():
    args = parse_args()
    cut_corpus(os.path.join(BASE_DIR, args.raw),
               os.path.join(BASE_DIR, args.out_dir),
               granularity=args.granularity,
               seed=args.seed,
               report_boundaries=args.report_boundaries)


if __name__ == "__main__":
    main()
