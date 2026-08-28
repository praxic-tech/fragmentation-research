"""
grid_common.py — shared plumbing for the strategy cutters.

Splitters here mirror Arafat's cutter.py / coherence_sever.py exactly, so
"reference fragment count" (used by random_cut.py) and unit boundaries (used
by subject_verb.py) line up with what semantic/coherence-sever actually
produce on the same document. Kept in one place instead of copy-pasted a
third time so the three files can't quietly drift apart.
"""
import json
import os

try:
    import spacy as _spacy
    _NLP = _spacy.load("en_core_web_sm")
    SPACY_AVAILABLE = True
except (ImportError, OSError):
    _NLP = None
    SPACY_AVAILABLE = False

import re


def get_nlp():
    if not SPACY_AVAILABLE:
        raise RuntimeError("spaCy / en_core_web_sm not available")
    return _NLP


def split_sentences(text):
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    return [s.strip() for s in sentences if s.strip()]


def split_clauses(text):
    if not SPACY_AVAILABLE:
        print("[warn] spaCy not available — falling back to sentence splitting for clause granularity")
        return split_sentences(text)
    doc = _NLP(text)
    fragments = []
    for sent in doc.sents:
        split_points = set()
        for token in sent:
            if token.dep_ == "conj" and token.pos_ == "VERB":
                for child in token.head.children:
                    if child.dep_ == "cc" and child.i < token.i:
                        split_points.add(child.i)
                        break
            if token.dep_ == "mark":
                split_points.add(token.i)
        start = sent.start
        for sp in sorted(split_points):
            chunk = doc[start:sp].text.strip()
            if chunk:
                fragments.append(chunk)
            start = sp
        tail = doc[start:sent.end].text.strip()
        if tail:
            fragments.append(tail)
    return [f for f in fragments if f]


def split_token_window(text, window_size=50):
    tokens = text.split()
    chunks = []
    for i in range(0, len(tokens), window_size):
        chunk = " ".join(tokens[i:i + window_size]).strip()
        if chunk:
            chunks.append(chunk)
    return chunks


def units_for_granularity(text, granularity, window_size=50):
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


def reference_fragment_count(text, granularity, window_size=50):
    return len(units_for_granularity(text, granularity, window_size=window_size))


def load_jsonl(path):
    with open(path, "r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def write_jsonl_pairs(records_fn, raw_records, out_dir, cell_name):
    """records_fn(record_id, text) -> list[str] fragments (in order).
    Writes fragments.jsonl + answer_key.jsonl in the standard schema and
    returns per-doc fragment counts for reporting."""
    os.makedirs(out_dir, exist_ok=True)
    frag_path = os.path.join(out_dir, "fragments.jsonl")
    key_path = os.path.join(out_dir, "answer_key.jsonl")

    frag_counts = []
    with open(frag_path, "w", encoding="utf-8") as ff, open(key_path, "w", encoding="utf-8") as kf:
        for rec in raw_records:
            record_id = rec["record_id"]
            fragments = records_fn(record_id, rec["text"])
            frag_counts.append(len(fragments))
            order = []
            for position, text in enumerate(fragments):
                fid = f"{record_id}__{cell_name}_{position:03d}"
                order.append(fid)
                ff.write(json.dumps({"fragment_id": fid, "record_id": record_id, "text": text}) + "\n")
            kf.write(json.dumps({"record_id": record_id, "order": order}) + "\n")

    return frag_path, key_path, frag_counts
