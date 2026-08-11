#!/usr/bin/env python3
"""
pull_prose_v4.py — prose_v4 corpus pull, instrumented for the (sigma x g) grid.

Fixes over the prose_v3 pull:
  1. FULL SOURCE TEXT SAVED. prose_documents.jsonl holds the complete untruncated
     case-narrative body per document, WITH paragraph breaks preserved as "\\n".
     prose_v3 saved only fragments, which made paragraph granularity
     unrecoverable and any re-cut impossible without re-fetching.
  2. NO REAL FRAGMENT CAP. --max-frags defaults to 100 (effectively uncapped) so
     the TRUE length distribution is observable. prose_v3's 12-cap truncated 96%
     of documents to a fake uniform length.
  3. REAL SENTENCE TOKENIZER. spaCy en_core_web_sm replaces the regex, which
     mis-split "Dr. Smith", "1.5 mg", "e.g." etc.
  4. Filters retained from prose_v3: case reports, commercial-use OA licence,
     post-January-2026 publication.

Also emits prose_meta.jsonl with per-document length metadata so document length
can be treated as an independent variable later without another pull.

Usage:
    python datagen/pull_prose_v4.py --target 500 --retmax 2600 --out data/prose
    python datagen/pull_prose_v4.py --target 500 --out data/prose --resume
"""

import argparse
import json
import re
import sys
import time
from pathlib import Path

# Reuse the networking / filtering layer from the v3 script WITHOUT modifying it.
from pull_prose import (search_pmids, pmids_to_pmcids, license_ok,
                        fetch_body_text, DEFAULT_MINDATE)

_NLP = None


def get_nlp():
    """Load spaCy once. Parser-based sentence boundaries handle clinical
    abbreviations ('Dr. Smith', '1.5 mg', 'e.g.') that the v3 regex split wrongly.
    Heavy components are excluded — we only need the parser for sentence bounds."""
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


def split_sentences(text, min_chars=15):
    """Sentence-split with spaCy, per paragraph so paragraph breaks are respected
    as hard boundaries (a sentence never straddles two paragraphs)."""
    nlp = get_nlp()
    out = []
    for para in text.split("\n"):
        para = re.sub(r"\s+", " ", para).strip()
        if not para:
            continue
        for sent in nlp(para).sents:
            s = sent.text.strip()
            if len(s) >= min_chars:
                out.append(s)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", type=int, default=500)
    ap.add_argument("--mindate", default=DEFAULT_MINDATE)
    ap.add_argument("--maxdate", default="2026/12")
    ap.add_argument("--min-frags", type=int, default=4,
                    help="skip documents shorter than this (kept from v3)")
    ap.add_argument("--max-frags", type=int, default=100,
                    help="UPPER BOUND ONLY — 100 is effectively uncapped. The real "
                         "bound is chosen from the observed percentiles afterwards, "
                         "not guessed here.")
    ap.add_argument("--retmax", type=int, default=None)
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--out", default="data/prose")
    args = ap.parse_args()

    outdir = Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)
    frag_p = outdir / "prose_fragments.jsonl"
    key_p  = outdir / "prose_answer_key.jsonl"
    doc_p  = outdir / "prose_documents.jsonl"
    meta_p = outdir / "prose_meta.jsonl"

    retmax = min(args.retmax or args.target * 5, 10000)
    print(f"[1/5] loading spaCy ...", flush=True)
    get_nlp()

    print(f"[2/5] searching PubMed (case reports, {args.mindate}-{args.maxdate}) ...",
          flush=True)
    pmids = search_pmids(args.mindate, args.maxdate, retmax)
    print(f"      {len(pmids)} PMIDs found", flush=True)

    print("[3/5] converting PMID -> PMCID ...", flush=True)
    pmcids = list(dict.fromkeys(pmids_to_pmcids(pmids).values()))
    print(f"      {len(pmcids)} have PMC full text", flush=True)

    done, kept = set(), 0
    if args.resume and key_p.exists():
        for line in key_p.open(encoding="utf-8"):
            if line.strip():
                done.add(json.loads(line).get("source_pmcid"))
                kept += 1
        print(f"      resuming: {kept} documents already on disk", flush=True)

    mode = "a" if (args.resume and kept) else "w"
    fh_frag = frag_p.open(mode, encoding="utf-8")
    fh_key  = key_p.open(mode, encoding="utf-8")
    fh_doc  = doc_p.open(mode, encoding="utf-8")
    fh_meta = meta_p.open(mode, encoding="utf-8")

    print(f"[4/5] fetching (cap={args.max_frags}, effectively uncapped) ...", flush=True)
    for idx, pmcid in enumerate(pmcids):
        if kept >= args.target:
            break
        if pmcid in done or not license_ok(pmcid):
            continue

        t0 = time.perf_counter()
        body = fetch_body_text(pmcid, case_only=True)   # paragraphs joined by "\n"
        if not body:
            continue
        all_sents = split_sentences(body)          # split ONCE, uncapped
        if len(all_sents) < args.min_frags:
            continue
        n_full = len(all_sents)                    # TRUE length, before any cap
        sents = all_sents[:args.max_frags]
        build_s = time.perf_counter() - t0

        rec = f"prose_{kept:04d}"
        order = []
        for j, s in enumerate(sents):
            fid = f"{rec}_frag_{j:03d}"
            order.append(fid)
            fh_frag.write(json.dumps({"record_id": rec, "fragment_id": fid,
                                      "text": s}) + "\n")
        fh_key.write(json.dumps({"record_id": rec, "order": order,
                                 "source_pmcid": pmcid}) + "\n")
        # FULL untruncated body, paragraph breaks preserved -> enables re-cutting
        # at any strategy/granularity, including paragraph.
        fh_doc.write(json.dumps({"record_id": rec, "source_pmcid": pmcid,
                                 "text": body}) + "\n")
        chars = [len(s) for s in sents]
        fh_meta.write(json.dumps({
            "record_id": rec,
            "source_pmcid": pmcid,
            "n_fragments": len(sents),
            "total_chars": sum(chars),
            "total_words": sum(len(s.split()) for s in sents),
            "mean_fragment_chars": round(sum(chars) / len(chars), 2),
            "doc_chars_full": len(body),
            # n_sentences_full is the TRUE uncapped sentence count. n_fragments is
            # what was written (== n_sentences_full unless the cap bit). The
            # percentile analysis must use n_sentences_full, otherwise the length
            # distribution is itself truncated by the very cap we're measuring.
            "n_sentences_full": n_full,
            "truncated": n_full > args.max_frags,
            "build_seconds": round(build_s, 4),
        }) + "\n")
        for fh in (fh_frag, fh_key, fh_doc, fh_meta):
            fh.flush()
        kept += 1
        if kept % 50 == 0:
            print(f"      kept {kept}/{args.target}  (scanned {idx+1})", flush=True)

    for fh in (fh_frag, fh_key, fh_doc, fh_meta):
        fh.close()
    print(f"[5/5] done: {kept} documents -> {outdir}", flush=True)
    print(f"      wrote prose_fragments / prose_answer_key / prose_documents / prose_meta",
          flush=True)


if __name__ == "__main__":
    main()
