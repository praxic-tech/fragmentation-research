"""
coherence_sever.py — the "coherence-sever" strategy for the fragmentation grid.

Same interface and I/O contract as Arafat's cutter.py so this drops in next to it:

    cut(text, strategy="coherence-sever", granularity="sentence", window_size=50) -> list[str]
    cut_corpus(raw_path, out_dir, ...) -> writes fragments.jsonl + answer_key.jsonl

Design (per spec: "cut at discourse links: pronoun-antecedent, however/therefore,
topic shifts"):

Other strategies either cut at every granularity-level boundary (semantic) or pick
boundaries with their own logic layered on top of the granularity units (random,
subject-verb). coherence-sever does the latter: it takes the granularity-level
units (sentence / clause / fixed token-window) as *candidate* boundaries, then
only actually cuts at the subset of those boundaries that carry a discourse link —
merging everything else into the same fragment. The result: fragments that break
exactly at points that would help a solver reorder them (a connective, a pronoun
needing its antecedent), rather than at arbitrary or purely structural seams.

A boundary between two adjacent units counts as a discourse link if any of:
  - the next unit opens with a discourse connective ("however", "therefore", ...)
  - the next unit opens with a pronoun needing an external antecedent
  - lexical (content-word) overlap between the two units drops below a threshold,
    read as a topic shift

sentence / clause: candidate boundaries = the granularity's own unit boundaries;
    cut only at the ones carrying a discourse link, merge the rest.
token-window: candidate boundaries = fixed window edges (window_size tokens);
    each edge is snapped to the nearest discourse-link token within a small
    search radius, so windows land on coherence breaks instead of arbitrary
    token counts. Falls back to the raw edge if nothing discourse-bearing is
    nearby, so the window-size contract is still roughly honored.

If a document has no discourse links at all, coherence-sever degrades to a
single whole-document fragment (documented, not silent) — there's nothing to
sever.

Install requirements: same as cutter.py (pip install spacy && python -m spacy
download en_core_web_sm). Falls back to sentence-only splitting if spaCy is
unavailable, same as Arafat's module.
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "datagen"))
from prose_cutter import split_sentences as _split_sentences, split_clauses as _split_clauses, DEFAULT_WINDOW  # noqa: E402

try:
    import spacy as _spacy
    _NLP = _spacy.load("en_core_web_sm")
    SPACY_AVAILABLE = True
except (ImportError, OSError):
    _NLP = None
    SPACY_AVAILABLE = False

DISCOURSE_CONNECTIVES = {
    "however", "therefore", "moreover", "meanwhile", "nevertheless", "furthermore",
    "consequently", "thus", "nonetheless", "similarly", "subsequently", "accordingly",
    "additionally", "conversely", "otherwise", "instead", "afterward", "afterwards",
    "then", "finally", "eventually", "later", "in contrast", "as a result",
    "on the other hand", "in addition", "for example", "for instance", "in fact",
    "at the same time", "by contrast",
}

PRONOUNS_NEEDING_ANTECEDENT = {
    "he", "she", "it", "they", "him", "her", "them", "his", "hers", "its", "their",
    "this", "that", "these", "those", "such",
}

STOPWORDS = {
    "the", "a", "an", "is", "are", "was", "were", "of", "to", "in", "on", "at",
    "and", "or", "but", "with", "for", "as", "by", "from", "that", "this", "it",
    "be", "has", "have", "had", "his", "her", "its", "their", "he", "she", "they",
}


# ── splitters from datagen/prose_cutter — do not reimplement ─────────────────
# _split_sentences and _split_clauses imported at the top of this file.


# ── discourse-link detection ────────────────────────────────────────────────

def _opens_with_connective(unit):
    lowered = unit.strip().lower()
    for c in DISCOURSE_CONNECTIVES:
        if lowered.startswith(c + " ") or lowered.startswith(c + ","):
            return True
    return False


def _opens_with_bare_pronoun(unit):
    first = re.match(r"[A-Za-z']+", unit.strip().lower())
    return bool(first and first.group(0) in PRONOUNS_NEEDING_ANTECEDENT)


def _content_words(unit):
    return {w for w in re.findall(r"[a-z']+", unit.lower()) if w not in STOPWORDS and len(w) > 2}


def _is_topic_shift(prev_unit, next_unit, overlap_threshold=0.12):
    prev_words, next_words = _content_words(prev_unit), _content_words(next_unit)
    if not prev_words or not next_words:
        return False
    jaccard = len(prev_words & next_words) / len(prev_words | next_words)
    return jaccard < overlap_threshold


def is_discourse_boundary(prev_unit, next_unit):
    """True if the boundary between these two adjacent units carries a discourse
    link worth severing at: a connective, a dangling pronoun, or a topic shift."""
    return (
        _opens_with_connective(next_unit)
        or _opens_with_bare_pronoun(next_unit)
        or _is_topic_shift(prev_unit, next_unit)
    )


# ── strategy implementation ─────────────────────────────────────────────────

def _cut_by_units(text, granularity):
    """sentence/clause granularity: merge adjacent units unless the boundary
    between them is a discourse link. Returns (fragments, fired, total_boundaries)
    so callers can report how often a boundary actually got cut at."""
    units = _split_sentences(text) if granularity == "sentence" else _split_clauses(text)
    if len(units) <= 1:
        return (units or [text.strip()]), 0, 0

    fragments, current, fired = [], units[0], 0
    total_boundaries = len(units) - 1
    for prev_unit, next_unit in zip(units, units[1:]):
        if is_discourse_boundary(prev_unit, next_unit):
            fragments.append(current)
            current = next_unit
            fired += 1
        else:
            current = f"{current} {next_unit}"
    fragments.append(current)
    return fragments, fired, total_boundaries


def _find_discourse_tokens(doc):
    """Token indices in a spaCy doc that open a discourse connective or a
    dangling pronoun — candidate snap points for token-window edges."""
    hits = []
    for i, tok in enumerate(doc):
        low = tok.text.lower()
        if low in DISCOURSE_CONNECTIVES or low in PRONOUNS_NEEDING_ANTECEDENT:
            hits.append(i)
    return hits


def _cut_token_window(text, window_size=50, snap_radius=10):
    """Fixed-size token windows whose edges are snapped to the nearest
    discourse-link token within snap_radius, so windows land on coherence
    breaks rather than arbitrary token counts. Falls back to the raw edge
    (Arafat's plain token-window behavior) if nothing is nearby."""
    if not SPACY_AVAILABLE:
        print("[warn] spaCy not available — falling back to plain token-window (no snapping)")
        tokens = text.split()
        return [" ".join(tokens[i:i + window_size]).strip()
                for i in range(0, len(tokens), window_size) if tokens[i:i + window_size]]

    doc = _NLP(text)
    n = len(doc)
    discourse_tokens = _find_discourse_tokens(doc)

    edges = [0]
    pos = window_size
    while pos < n:
        nearby = [t for t in discourse_tokens if abs(t - pos) <= snap_radius and t > edges[-1]]
        edge = min(nearby, key=lambda t: abs(t - pos)) if nearby else pos
        if edge > edges[-1]:
            edges.append(edge)
        pos = edge + window_size
    edges.append(n)

    fragments = []
    for start, end in zip(edges, edges[1:]):
        chunk = doc[start:end].text.strip()
        if chunk:
            fragments.append(chunk)
    return fragments


def cut(text, strategy="coherence-sever", granularity="sentence", window_size=50):
    """coherence-sever: cut only at discourse-link boundaries (connective,
    dangling pronoun, topic shift) within the given granularity's candidate
    boundaries. See module docstring for the token-window snapping behavior."""
    if granularity in ("sentence", "clause"):
        fragments, _fired, _total = _cut_by_units(text, granularity)
        return fragments
    elif granularity == "token-window":
        return _cut_token_window(text, window_size=window_size)
    else:
        raise ValueError(
            f"Unknown granularity '{granularity}'. Choose from: sentence, clause, token-window"
        )


# ── corpus-level runner (mirrors cutter.py's cut_corpus exactly) ───────────

def load_jsonl(path):
    with open(path, "r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def cut_corpus(raw_path, out_dir, granularity="sentence", window_size=None,
               docs=None, report_boundaries=False, **_):
    """
    docs: optional list of record_ids (pool selection from build_pools.py).
    Outputs prose_fragments.jsonl + prose_answer_key.jsonl (exact harness names).
    window_size defaults to DEFAULT_WINDOW from datagen/prose_cutter.
    """
    if window_size is None:
        window_size = DEFAULT_WINDOW
    os.makedirs(out_dir, exist_ok=True)
    records = load_jsonl(raw_path)

    if docs is not None:
        doc_set = set(docs)
        records = [r for r in records if r["record_id"] in doc_set]

    frag_path = os.path.join(out_dir, "prose_fragments.jsonl")
    key_path  = os.path.join(out_dir, "prose_answer_key.jsonl")

    total_frags = 0
    frag_counts = []
    fire_stats = {"fired": 0, "total_boundaries": 0}
    with open(frag_path, "w", encoding="utf-8") as ff, open(key_path, "w", encoding="utf-8") as kf:
        for rec in records:
            record_id = rec["record_id"]
            if granularity in ("sentence", "clause"):
                fragments, fired, total_b = _cut_by_units(rec["text"], granularity)
                fire_stats["fired"] += fired
                fire_stats["total_boundaries"] += total_b
            else:
                fragments = _cut_token_window(rec["text"], window_size=window_size)
            frag_counts.append(len(fragments))

            order = []
            for position, text in enumerate(fragments):
                fid = f"{record_id}__cs_{granularity}_{position:03d}"
                order.append(fid)
                ff.write(json.dumps({"fragment_id": fid, "record_id": record_id, "text": text}) + "\n")
                total_frags += 1
            kf.write(json.dumps({"record_id": record_id, "order": order}) + "\n")

    n_docs = len(records)
    print(f"[coherence-sever x {granularity}]  "
          f"{n_docs} docs -> {total_frags} fragments  "
          f"(min={min(frag_counts)}, max={max(frag_counts)}, "
          f"mean={sum(frag_counts)/n_docs:.1f})")
    print(f"  wrote: {frag_path}")
    print(f"  wrote: {key_path}")

    if report_boundaries and granularity in ("sentence", "clause"):
        total_b = fire_stats["total_boundaries"]
        rate = (fire_stats["fired"] / total_b) if total_b else 0.0
        print(f"  [report] discourse-boundary fire rate: {fire_stats['fired']}/{total_b} "
              f"candidate boundaries cut ({rate:.1%})")
        if rate < 0.20:
            print(f"  [report] WARNING: fire rate {rate:.1%} is under ~20% — likely collapsed.")

    return {"n_docs": n_docs, "n_fragments": total_frags}


# ── CLI (matches cutter.py's flags, strategy fixed to coherence-sever) ─────

def parse_args():
    parser = argparse.ArgumentParser(description="Cut a prose corpus with the coherence-sever strategy.")
    parser.add_argument("--raw", default="prose_raw.jsonl")
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--granularity", default="sentence",
                        choices=["sentence", "clause", "token-window"])
    parser.add_argument("--window-size", type=int, default=None,
                        help="token window size (defaults to DEFAULT_WINDOW from datagen/prose_cutter)")
    parser.add_argument("--report-boundaries", action="store_true",
                        help="report the discourse-boundary fire rate (sentence/clause only)")
    return parser.parse_args()


def main():
    args = parse_args()
    cut_corpus(
        os.path.join(BASE_DIR, args.raw),
        os.path.join(BASE_DIR, args.out_dir),
        granularity=args.granularity,
        window_size=args.window_size,
        report_boundaries=args.report_boundaries,
    )


if __name__ == "__main__":
    main()
