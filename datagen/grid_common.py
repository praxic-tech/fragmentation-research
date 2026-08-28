"""
grid_common.py — shared plumbing for the strategy cutters.

REBASED onto the post-restructure repo (was: own regex splitters).

ONE TOKENIZER, ONE SENTENCE BASE
--------------------------------
The splitters are IMPORTED from datagen/prose_cutter.py, never reimplemented.
This is not a style preference — it is bug 2 from the week-6 bug list. The
previous version of this file split sentences with

    re.split(r'(?<=[.!?])\\s+', text)

while splitting clauses with spaCy. Measured against the real corpus, those two
rulers disagreed on the sentence count for 92 of 100 documents, produced 12.7%
more fragments overall, and on 22 of 100 documents the supposedly FINER clause
cut produced FEWER fragments than the coarser sentence cut. The granularity axis
stops measuring granularity and starts measuring a change of ruler.

It also silently voids random_cut's rate matching: reference_fragment_count()
below is what random_cut targets, and if it is computed with a different
splitter than the reference cell actually used, the counts are matched against
the wrong thing on 92% of documents.

The shared base also applies MIN_SENT_CHARS and splits per paragraph so a
sentence never straddles a paragraph break — both of which the regex ignored.
"""
import json
import os
import sys

_DATAGEN = os.path.dirname(os.path.abspath(__file__))
if _DATAGEN not in sys.path:
    sys.path.insert(0, _DATAGEN)

from prose_cutter import (          # noqa: E402 — one tokenizer for the whole grid
    DEFAULT_WINDOW,
    _nlp,
    _split_clauses,
    _split_sentences,
    _split_token_window,
)

# Re-exported under the names the cutters already use.
get_nlp = _nlp
split_sentences = _split_sentences
split_clauses = _split_clauses


def split_token_window(text, window_size=DEFAULT_WINDOW):
    return _split_token_window(text, window_size=window_size)


def units_for_granularity(text, granularity, window_size=DEFAULT_WINDOW):
    """The 'natural'/semantic unit split for a granularity — this is what
    random_cut.py treats as the reference fragment count to match."""
    if granularity == "sentence":
        return split_sentences(text)
    elif granularity == "clause":
        return split_clauses(text)
    elif granularity == "token-window":
        return split_token_window(text, window_size=window_size)
    else:
        raise ValueError(f"unknown granularity: {granularity!r}")


def reference_fragment_count(text, granularity, window_size=DEFAULT_WINDOW):
    return len(units_for_granularity(text, granularity, window_size=window_size))


def load_jsonl(path):
    with open(path, "r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def write_jsonl_pairs(records_fn, raw_records, out_dir, cell_name=None):
    """records_fn(record_id, text) -> list[str] fragments (in order).

    Writes prose_fragments.jsonl + prose_answer_key.jsonl in the corpus schema.
    The filenames and the fragment-id format are NOT free choices: they are the
    contract `harness/run_baselines.py --data <cell>` reads, and it hard-exits
    on anything else. cell_name is accepted and ignored — it used to go into the
    fragment id, which broke that contract.

    Returns (frag_path, key_path, per_doc_fragment_counts).
    """
    os.makedirs(out_dir, exist_ok=True)
    frag_path = os.path.join(out_dir, "prose_fragments.jsonl")
    key_path = os.path.join(out_dir, "prose_answer_key.jsonl")

    frag_counts = []
    with open(frag_path, "w", encoding="utf-8") as ff, \
         open(key_path, "w", encoding="utf-8") as kf:
        for rec in raw_records:
            record_id = rec["record_id"]
            fragments = records_fn(record_id, rec["text"])
            frag_counts.append(len(fragments))
            order = []
            for position, text in enumerate(fragments):
                fid = f"{record_id}_frag_{position:03d}"
                order.append(fid)
                ff.write(json.dumps({"record_id": record_id,
                                     "fragment_id": fid,
                                     "text": text}) + "\n")
            kf.write(json.dumps({"record_id": record_id, "order": order}) + "\n")

    return frag_path, key_path, frag_counts
