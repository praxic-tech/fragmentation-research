"""
Prose document cutter for the fragmentation reassembly grid (Part A).

Implements the shared cutter interface:
    cut(text, strategy, granularity) -> list[str]

and a corpus-level runner that emits standard JSONL (fragments + answer key)
so the harness runs unchanged across grid cells.

Granularities:
    sentence     -- one sentence per fragment
    clause       -- clause-level splits inside each sentence
    token-window -- fixed k-token windows, structure-blind

Strategies implemented here:
    semantic     -- boundary falls at the natural linguistic unit
                    (i.e. the granularity itself determines the cut)

Other strategies (random, coherence-sever, subject-verb, llm-cut) call cut()
with the same granularity values and supply their own boundary-selection logic
on top. coherence_sever.py imports the splitters below rather than reimplementing
them, so every strategy shares one tokenizer.

ONE TOKENIZER, ONE SENTENCE BASE
--------------------------------
Sentence boundaries come from spaCy's parser, per paragraph, with the same
min-15-character rule the corpus itself was built with (see
`pull_prose_v4.split_sentences`). Two consequences that the grid depends on:

  * `semantic x sentence` reproduces the corpus's own fragmentation exactly, so
    the reference cell IS the corpus rather than a second opinion about it.
  * `clause` subdivides those same sentence units, so the granularity axis runs
    strictly coarse -> fine. A document can never yield fewer clause fragments
    than sentence fragments.

An earlier version split sentences with a regex while splitting clauses with
spaCy. That disagreed with the corpus on 342 of 500 documents and inverted the
granularity axis on 50 of them, which would have made every comparison against
the reference cell meaningless.

Install requirements:
    pip install spacy
    python -m spacy download en_core_web_sm

Usage (from the repo root; --raw defaults to data/prose/prose_raw.jsonl):
    python datagen/prose_cutter.py \\
        --out-dir results/grid/semantic_clause \\
        --strategy semantic \\
        --granularity clause

    python datagen/prose_cutter.py \\
        --out-dir results/grid/semantic_token_window \\
        --strategy semantic \\
        --granularity token-window \\
        --window-size 12
"""

import argparse
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # repo root

DEFAULT_RAW = os.path.join(ROOT, "data", "prose", "prose_raw.jsonl")

# Matches the corpus build (pull_prose_v4.split_sentences). Changing this
# desynchronises the reference cell from the corpus.
MIN_SENT_CHARS = 15

# RUN_PLAN pins k = 12: below the mean sentence length, so token-window is the
# *finest* cut. At larger k it is coarser than a sentence and the axis inverts.
DEFAULT_WINDOW = 12

_NLP = None


def _nlp():
    """Load spaCy once. Parser-based sentence boundaries handle clinical
    abbreviations ('Dr. Smith', '1.5 mg', 'e.g.'); a regex does not. Heavy
    components are excluded — only the parser is needed."""
    global _NLP
    if _NLP is None:
        try:
            import spacy
        except ImportError:
            sys.exit("ERROR: spaCy not installed.  pip install spacy && "
                     "python -m spacy download en_core_web_sm")
        try:
            _NLP = spacy.load("en_core_web_sm",
                              exclude=["ner", "lemmatizer", "textcat"])
        except OSError:
            sys.exit("ERROR: model missing.  python -m spacy download en_core_web_sm")
        _NLP.max_length = 2_000_000
    return _NLP


# ── granularity splitters ────────────────────────────────────────────────────────

def _split_sentences(text):
    """Sentence-split with spaCy, per paragraph so paragraph breaks are hard
    boundaries (a sentence never straddles two paragraphs). Identical to the
    corpus build, so `semantic x sentence` reproduces the corpus."""
    nlp = _nlp()
    out = []
    for para in text.split("\n"):
        para = re.sub(r"\s+", " ", para).strip()
        if not para:
            continue
        for sent in nlp(para).sents:
            s = sent.text.strip()
            if len(s) >= MIN_SENT_CHARS:
                out.append(s)
    return out


def _clause_pieces(sentence):
    """Split one sentence into clauses. Cuts at:
      - coordinating conjunctions joining verb phrases
        "She walked in and sat down" -> ["She walked in", "and sat down"]
      - subordinate clause markers
        "He rested because he was tired" -> ["He rested", "because he was tired"]

    Always returns at least one piece, so clause never comes out coarser than
    sentence.
    """
    doc = _nlp()(sentence)
    split_points = set()

    for token in doc:
        # coordinated verb clause: find the cc token before a conj VERB
        if token.dep_ == "conj" and token.pos_ == "VERB":
            for child in token.head.children:
                if child.dep_ == "cc" and child.i < token.i:
                    split_points.add(child.i)
                    break

        # subordinate clause marker: "because", "although", "while", ...
        if token.dep_ == "mark":
            split_points.add(token.i)

    pieces, start = [], 0
    for sp in sorted(split_points):
        chunk = doc[start:sp].text.strip()
        if chunk:
            pieces.append(chunk)
        start = sp
    tail = doc[start:].text.strip()
    if tail:
        pieces.append(tail)

    return pieces or [sentence.strip()]


def _split_clauses(text):
    """Clause fragments, derived from the same sentence units as
    _split_sentences — so the granularity axis is strictly coarse -> fine."""
    fragments = []
    for sentence in _split_sentences(text):
        fragments.extend(_clause_pieces(sentence))
    return fragments


def _split_token_window(text, window_size=DEFAULT_WINDOW):
    """Split text into fixed-size token windows (whitespace tokenisation).

    window_size: number of tokens per fragment. The last window may be shorter.
    Structure-blind: cuts across sentence and clause boundaries, which is the
    point — it is the granularity that carries no linguistic unit at all.
    """
    tokens = text.split()
    chunks = []
    for i in range(0, len(tokens), window_size):
        chunk = " ".join(tokens[i:i + window_size]).strip()
        if chunk:
            chunks.append(chunk)
    return chunks


# ── public interface ─────────────────────────────────────────────────────────────

def cut(text, strategy="semantic", granularity="sentence",
        window_size=DEFAULT_WINDOW):
    """Cut a raw document body into a list of fragment strings.

    Args:
        text        : raw document body (full, unsplit text)
        strategy    : cutting strategy ("semantic", "random", ...)
                      For this module, "semantic" uses the natural linguistic
                      unit determined by granularity. Other strategies are
                      implemented externally and call cut() as a sub-step.
        granularity : "sentence" | "clause" | "token-window"
        window_size : token count per window (token-window only)

    Returns:
        list[str] — ordered fragment strings in their original document order
    """
    if granularity == "sentence":
        return _split_sentences(text)
    elif granularity == "clause":
        return _split_clauses(text)
    elif granularity == "token-window":
        return _split_token_window(text, window_size=window_size)
    else:
        raise ValueError(
            f"Unknown granularity '{granularity}'. "
            "Choose from: sentence, clause, token-window"
        )


# ── corpus-level runner ──────────────────────────────────────────────────────────

def load_jsonl(path):
    with open(path, "r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def cut_corpus(raw_path, out_dir, strategy="semantic",
               granularity="sentence", window_size=DEFAULT_WINDOW):
    """Cut every record in prose_raw.jsonl and emit standard JSONL.

    Outputs to out_dir:
        prose_fragments.jsonl  -- {record_id, fragment_id, text}
        prose_answer_key.jsonl -- {record_id, order: [fragment_id, ...]}

    Names and schema match data/prose/, so any runner that reads the corpus
    reads a grid cell without translation.
    """
    os.makedirs(out_dir, exist_ok=True)
    records = load_jsonl(raw_path)

    frag_path = os.path.join(out_dir, "prose_fragments.jsonl")
    key_path  = os.path.join(out_dir, "prose_answer_key.jsonl")

    total_frags = 0
    frag_counts = []
    with open(frag_path, "w", encoding="utf-8") as ff, \
         open(key_path,  "w", encoding="utf-8") as kf:

        for rec in records:
            record_id = rec["record_id"]
            fragments = cut(rec["text"], strategy=strategy,
                            granularity=granularity, window_size=window_size)
            frag_counts.append(len(fragments))

            order = []
            for position, text in enumerate(fragments):
                fid = f"{record_id}_frag_{position:03d}"
                order.append(fid)
                ff.write(json.dumps({"record_id":   record_id,
                                     "fragment_id": fid,
                                     "text":        text}) + "\n")
                total_frags += 1
            kf.write(json.dumps({"record_id": record_id, "order": order}) + "\n")

    print(f"[{strategy} x {granularity}]  "
          f"{len(records)} records -> {total_frags} fragments  "
          f"(min={min(frag_counts)}, max={max(frag_counts)}, "
          f"mean={sum(frag_counts)/len(frag_counts):.1f})")
    print(f"  wrote: {frag_path}")
    print(f"  wrote: {key_path}")


# ── CLI ──────────────────────────────────────────────────────────────────────────

def parse_args():
    parser = argparse.ArgumentParser(
        description="Cut a prose corpus for the reassembly grid."
    )
    parser.add_argument("--raw",         default=DEFAULT_RAW,
                        help="prose_raw.jsonl (default: data/prose/prose_raw.jsonl)")
    parser.add_argument("--out-dir",     required=True,
                        help="output directory for fragments + answer key")
    parser.add_argument("--strategy",    default="semantic",
                        help="cut strategy label (semantic, random, ...)")
    parser.add_argument("--granularity", default="sentence",
                        choices=["sentence", "clause", "token-window"],
                        help="granularity: sentence | clause | token-window")
    parser.add_argument("--window-size", type=int, default=DEFAULT_WINDOW,
                        help=f"tokens per window, token-window only (default {DEFAULT_WINDOW})")
    return parser.parse_args()


def main():
    args = parse_args()
    # CLI paths are taken as given (relative to the current working directory);
    # only the defaults are anchored to the repo root.
    cut_corpus(args.raw, args.out_dir,
               strategy=args.strategy,
               granularity=args.granularity,
               window_size=args.window_size)


if __name__ == "__main__":
    main()
