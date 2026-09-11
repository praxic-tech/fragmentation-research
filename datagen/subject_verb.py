"""
subject_verb.py — the "subject-verb" strategy for the fragmentation grid.

    cut(text, granularity) -> list[str]

Splitters come from datagen/prose_cutter.py — never reimplemented here.

Rule: within each granularity unit (sentence or clause — token-window is
"skip" in the grid), scan tokens for dep_ == "nsubj". On the first nsubj
found, cut right before token.head (the governing verb). That produces
(subject phrase) | (verb onward) as two fragments for that unit.

nsubj only, not nsubjpass. On 40 real case-report docs the rates are:
    sentence:  nsubj-only 72.1%   nsubj+nsubjpass 89.4%
    clause:    nsubj-only 65.2%   nsubj+nsubjpass 85.2%
Both clear the 20% collapse floor. nsubjpass was excluded because the
original spec said nsubj — not because it was tested. Given these are
medical reports ("the patient was admitted", "a biopsy was performed")
the exclusion is worth revisiting with the team, but it doesn't change
whether we pay for the cell either way.

No-match units: emitted whole, never substituted with a sentence boundary.
That fallback would make a unit look like it got a subject-verb cut when
it didn't, hiding the actual fire rate.

Fire stats are tracked in cut_corpus, not returned from cut(). cut()
returns list[str] only, consistent with every other strategy's interface.
"""

import argparse
import json
import os
import sys
from pathlib import Path

# splitters from the shared source — same instance the reference cell uses
_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "datagen"))
from prose_cutter import split_sentences, split_clauses  # noqa: E402

try:
    import spacy as _spacy
    _NLP = _spacy.load("en_core_web_sm")
except (ImportError, OSError) as e:
    raise RuntimeError("spaCy / en_core_web_sm required for subject_verb.py") from e

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _cut_unit(unit_text):
    """Returns (list[str], fired:bool). list is length 1 (no cut) or 2 (cut)."""
    doc = _NLP(unit_text)
    for tok in doc:
        if tok.dep_ == "nsubj":
            head = tok.head
            # The cut must fall on WHITESPACE in the source. spaCy splits
            # "patient’s" and "MP™" into tokens with no gap between them; a cut
            # there made the rejoin insert a space, and 4 frame-A documents
            # failed exact reconstruction. Same rule coherence-sever uses.
            if head.i > 0 and doc[head.i - 1].whitespace_:
                pre = doc[:head.i].text.strip()
                post = doc[head.i:].text.strip()
                if pre and post:
                    return [pre, post], True
    return [unit_text.strip()], False


def cut(text, granularity="sentence"):
    """Cut text using the subject-verb strategy. Returns list[str]."""
    if granularity == "token-window":
        raise ValueError(
            "subject-verb x token-window is 'skip' in the grid — not implemented by design"
        )
    if granularity not in ("sentence", "clause"):
        raise ValueError(f"unknown granularity for subject-verb: {granularity!r}")

    units = split_sentences(text) if granularity == "sentence" else split_clauses(text)
    fragments = []
    for unit in units:
        pieces, _ = _cut_unit(unit)
        fragments.extend(pieces)
    return fragments


def cut_corpus(raw_path, out_dir, granularity="sentence", docs=None,
               report_boundaries=False):
    """
    docs: optional list of record_ids to restrict cutting to (--docs hook
          for pool selection from build_pools.py). None means all records.
    Outputs prose_fragments.jsonl + prose_answer_key.jsonl (exact harness names).
    """
    os.makedirs(out_dir, exist_ok=True)

    with open(raw_path, "r", encoding="utf-8") as f:
        records = [json.loads(l) for l in f if l.strip()]

    if docs is not None:
        doc_set = set(docs)
        records = [r for r in records if r["record_id"] in doc_set]

    frag_path = os.path.join(out_dir, "prose_fragments.jsonl")
    key_path = os.path.join(out_dir, "prose_answer_key.jsonl")

    frag_counts, fire_stats = [], {"fired": 0, "total_units": 0}

    with open(frag_path, "w", encoding="utf-8") as ff, \
         open(key_path, "w", encoding="utf-8") as kf:
        for rec in records:
            record_id = rec["record_id"]
            units = (split_sentences(rec["text"]) if granularity == "sentence"
                     else split_clauses(rec["text"]))
            fire_stats["total_units"] += len(units)

            fragments, order = [], []
            for unit in units:
                pieces, fired = _cut_unit(unit)
                fragments.extend(pieces)
                fire_stats["fired"] += int(fired)

            frag_counts.append(len(fragments))
            for position, text in enumerate(fragments):
                fid = f"{record_id}__sv_{granularity}_{position:03d}"
                order.append(fid)
                ff.write(json.dumps({
                    "fragment_id": fid, "record_id": record_id, "text": text
                }) + "\n")
            kf.write(json.dumps({"record_id": record_id, "order": order}) + "\n")

    n_docs = len(records)
    n_frags = sum(frag_counts)
    fire_rate = (fire_stats["fired"] / fire_stats["total_units"]
                 if fire_stats["total_units"] else 0.0)

    print(f"[subject-verb x {granularity}]  {n_docs} docs -> {n_frags} fragments  "
          f"(min={min(frag_counts)}, max={max(frag_counts)}, "
          f"mean={sum(frag_counts)/n_docs:.1f})")
    print(f"  wrote: {frag_path}")
    print(f"  wrote: {key_path}")
    if report_boundaries:
        print(f"  [fire rate] {fire_stats['fired']}/{fire_stats['total_units']} "
              f"units cut ({fire_rate:.1%})")
        if fire_rate < 0.20:
            print(f"  [WARNING] fire rate under 20% — cell likely collapsed onto semantic")

    return {"n_docs": n_docs, "n_fragments": n_frags, "fire_rate": fire_rate}


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", default="prose_raw.jsonl")
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--granularity", default="sentence", choices=["sentence", "clause"])
    parser.add_argument("--report-boundaries", action="store_true")
    return parser.parse_args()


def main():
    args = parse_args()
    cut_corpus(os.path.join(BASE_DIR, args.raw),
               os.path.join(BASE_DIR, args.out_dir),
               granularity=args.granularity,
               report_boundaries=args.report_boundaries)


if __name__ == "__main__":
    main()
