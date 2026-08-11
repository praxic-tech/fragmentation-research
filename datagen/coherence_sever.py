"""
coherence_sever.py — the "coherence-sever" strategy for the fragmentation grid.

Same interface and I/O contract as prose_cutter.py so this drops in next to it:

    cut(text, strategy="coherence-sever", granularity="sentence", window_size=12) -> list[str]
    cut_corpus(raw_path, out_dir, ...) -> writes prose_fragments.jsonl + prose_answer_key.jsonl

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

The sentence and clause splitters are IMPORTED from prose_cutter rather than
reimplemented, so every strategy in the grid shares one spaCy tokenizer and one
sentence base. See the "ONE TOKENIZER, ONE SENTENCE BASE" note there.

CALIBRATION WARNING
-------------------
On short documents whose consecutive sentences share little vocabulary, the
`jaccard < TOPIC_SHIFT_THRESHOLD` test fires at nearly every boundary and
coherence-sever collapses onto semantic (measured: 101 fragments vs semantic's
104 on the 25-doc synthetic corpus). Check `--report-boundaries` output on the
real corpus before treating these as two distinct grid conditions.

Install requirements: same as prose_cutter.py (pip install spacy &&
python -m spacy download en_core_web_sm).
"""

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from prose_cutter import (            # noqa: E402  — one tokenizer for the whole grid
    DEFAULT_RAW,
    DEFAULT_WINDOW,
    ROOT,
    _nlp,
    _split_clauses,
    _split_sentences,
    load_jsonl,
)

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

TOPIC_SHIFT_THRESHOLD = 0.12


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


def _is_topic_shift(prev_unit, next_unit, overlap_threshold=TOPIC_SHIFT_THRESHOLD):
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


def boundary_reasons(units):
    """Which rule fired at each candidate boundary. Diagnostic for calibration —
    if 'topic_shift' fires nearly everywhere, the threshold needs lowering."""
    tally = {"connective": 0, "pronoun": 0, "topic_shift": 0, "none": 0}
    for prev_unit, next_unit in zip(units, units[1:]):
        if _opens_with_connective(next_unit):
            tally["connective"] += 1
        elif _opens_with_bare_pronoun(next_unit):
            tally["pronoun"] += 1
        elif _is_topic_shift(prev_unit, next_unit):
            tally["topic_shift"] += 1
        else:
            tally["none"] += 1
    return tally


# ── strategy implementation ─────────────────────────────────────────────────

def _cut_by_units(text, granularity):
    """sentence/clause granularity: merge adjacent units unless the boundary
    between them is a discourse link."""
    units = _split_sentences(text) if granularity == "sentence" else _split_clauses(text)
    if len(units) <= 1:
        return units or [text.strip()]

    fragments, current = [], units[0]
    for prev_unit, next_unit in zip(units, units[1:]):
        if is_discourse_boundary(prev_unit, next_unit):
            fragments.append(current)
            current = next_unit
        else:
            current = f"{current} {next_unit}"
    fragments.append(current)
    return fragments


def _find_discourse_tokens(doc):
    """Token indices in a spaCy doc that open a discourse connective or a
    dangling pronoun — candidate snap points for token-window edges."""
    hits = []
    for i, tok in enumerate(doc):
        low = tok.text.lower()
        if low in DISCOURSE_CONNECTIVES or low in PRONOUNS_NEEDING_ANTECEDENT:
            hits.append(i)
    return hits


def _cut_token_window(text, window_size=DEFAULT_WINDOW, snap_radius=3):
    """Fixed-size token windows whose edges are snapped to the nearest
    discourse-link token within snap_radius, so windows land on coherence
    breaks rather than arbitrary token counts. Falls back to the raw edge
    (plain token-window behavior) if nothing is nearby.

    snap_radius scales with the window: at k=12 a radius of 10 could drag an
    edge most of a window away, which stops being 'snapping'.
    """
    doc = _nlp()(re.sub(r"\s+", " ", text).strip())
    n = len(doc)
    discourse_tokens = _find_discourse_tokens(doc)
    radius = min(snap_radius, max(1, window_size // 4))

    edges = [0]
    pos = window_size
    while pos < n:
        nearby = [t for t in discourse_tokens if abs(t - pos) <= radius and t > edges[-1]]
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


def cut(text, strategy="coherence-sever", granularity="sentence",
        window_size=DEFAULT_WINDOW):
    """coherence-sever: cut only at discourse-link boundaries (connective,
    dangling pronoun, topic shift) within the given granularity's candidate
    boundaries. See module docstring for the token-window snapping behavior."""
    if granularity in ("sentence", "clause"):
        return _cut_by_units(text, granularity)
    elif granularity == "token-window":
        return _cut_token_window(text, window_size=window_size)
    else:
        raise ValueError(
            f"Unknown granularity '{granularity}'. Choose from: sentence, clause, token-window"
        )


# ── corpus-level runner (mirrors prose_cutter.cut_corpus exactly) ──────────

def cut_corpus(raw_path, out_dir, granularity="sentence",
               window_size=DEFAULT_WINDOW, report_boundaries=False):
    os.makedirs(out_dir, exist_ok=True)
    records = load_jsonl(raw_path)

    frag_path = os.path.join(out_dir, "prose_fragments.jsonl")
    key_path  = os.path.join(out_dir, "prose_answer_key.jsonl")

    total_frags = 0
    frag_counts = []
    tally = {"connective": 0, "pronoun": 0, "topic_shift": 0, "none": 0}

    with open(frag_path, "w", encoding="utf-8") as ff, \
         open(key_path,  "w", encoding="utf-8") as kf:

        for rec in records:
            record_id = rec["record_id"]
            fragments = cut(rec["text"], granularity=granularity,
                            window_size=window_size)
            frag_counts.append(len(fragments))

            if report_boundaries and granularity in ("sentence", "clause"):
                units = (_split_sentences(rec["text"]) if granularity == "sentence"
                         else _split_clauses(rec["text"]))
                for k, v in boundary_reasons(units).items():
                    tally[k] += v

            order = []
            for position, text in enumerate(fragments):
                fid = f"{record_id}_frag_{position:03d}"
                order.append(fid)
                ff.write(json.dumps({"record_id":   record_id,
                                     "fragment_id": fid,
                                     "text":        text}) + "\n")
                total_frags += 1
            kf.write(json.dumps({"record_id": record_id, "order": order}) + "\n")

    print(f"[coherence-sever x {granularity}]  "
          f"{len(records)} records -> {total_frags} fragments  "
          f"(min={min(frag_counts)}, max={max(frag_counts)}, "
          f"mean={sum(frag_counts)/len(frag_counts):.1f})")
    print(f"  wrote: {frag_path}")
    print(f"  wrote: {key_path}")

    if report_boundaries and sum(tally.values()):
        total = sum(tally.values())
        print("  boundary rule that fired (share of candidate boundaries):")
        for k, v in tally.items():
            print(f"    {k:12s} {v:7d}  {v/total:6.1%}")
        cut_share = (total - tally["none"]) / total
        print(f"    -> cuts at {cut_share:.1%} of boundaries; near 100% means "
              f"this cell has collapsed onto semantic")


# ── CLI (matches prose_cutter.py's flags, strategy fixed to coherence-sever) ─

def parse_args():
    parser = argparse.ArgumentParser(description="Cut a prose corpus with the coherence-sever strategy.")
    parser.add_argument("--raw", default=DEFAULT_RAW,
                        help="prose_raw.jsonl (default: data/prose/prose_raw.jsonl)")
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--granularity", default="sentence",
                        choices=["sentence", "clause", "token-window"])
    parser.add_argument("--window-size", type=int, default=DEFAULT_WINDOW)
    parser.add_argument("--report-boundaries", action="store_true",
                        help="report which discourse rule fired where (calibration check)")
    return parser.parse_args()


def main():
    args = parse_args()
    # CLI paths are taken as given (relative to the current working directory);
    # only the defaults are anchored to the repo root.
    cut_corpus(
        args.raw,
        args.out_dir,
        granularity=args.granularity,
        window_size=args.window_size,
        report_boundaries=args.report_boundaries,
    )


if __name__ == "__main__":
    main()
