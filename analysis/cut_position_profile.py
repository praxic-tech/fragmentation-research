#!/usr/bin/env python3
"""
cut_position_profile.py — where does a cut strategy actually cut?

NO API CALLS. Pure local computation over a cell's `prose_fragments.jsonl` and
the corpus `prose_raw.jsonl`. Runs in seconds on the full corpus.

Built for the `llm-cut` cell — when the model picks its own cut points, the
interesting question is what it converges on — but it profiles ANY cell, which
is the point: an llm-cut number means nothing without the rule-based strategies
to compare it against.

What it measures, per cell:

  granularity      fragments/doc, and words per fragment. Answers "what
                   granularity did this strategy actually land on" in the same
                   units as sentence / clause / token-window, so the LLM's
                   self-chosen granularity is directly comparable.

  boundary type    for each cut, the finest linguistic boundary it coincides
                   with: paragraph > sentence > clause > mid-clause. A strategy
                   that cuts mid-clause is destroying units that a strategy
                   cutting at paragraph breaks preserves.

  position         cut offsets normalised to [0,1] and binned into deciles.
                   Flat means position-blind; front- or back-loaded means the
                   strategy is treating some part of the document as special.

  first token      what word each fragment opens with — discourse connective,
                   pronoun needing an antecedent, or neither. A fragment opening
                   with "however" or "it" carries a dangling link that helps a
                   reassembler; the share of such openings is a direct measure
                   of how much ordering signal the cut leaves exposed.

Usage:
    python analysis/cut_position_profile.py --cell results/grid/llm_cut
    python analysis/cut_position_profile.py --cell results/grid/llm_cut \\
        --compare results/grid/semantic_sentence results/grid/semantic_clause
"""

import argparse
import json
import re
import statistics as st
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "datagen"))

DEFAULT_RAW = ROOT / "data" / "prose" / "prose_raw.jsonl"

# Same lists coherence_sever cuts on, so the two are directly comparable.
CONNECTIVES = {
    "however", "therefore", "moreover", "meanwhile", "nevertheless", "furthermore",
    "consequently", "thus", "nonetheless", "similarly", "subsequently", "accordingly",
    "additionally", "conversely", "otherwise", "instead", "afterward", "afterwards",
    "then", "finally", "eventually", "later",
}
PRONOUNS = {
    "he", "she", "it", "they", "him", "her", "them", "his", "hers", "its", "their",
    "this", "that", "these", "those", "such",
}


def load_jsonl(path):
    with open(path, "r", encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def _norm(s):
    """Whitespace-normalise so fragment text can be located in the raw body."""
    return re.sub(r"\s+", " ", s).strip()


def boundary_offsets(text):
    """Character offsets in the normalised body for paragraph / sentence /
    clause boundaries, so a cut can be classified against them."""
    from prose_cutter import _split_sentences, _split_clauses

    para_ends, pos = set(), 0
    for para in text.split("\n"):
        p = _norm(para)
        if not p:
            continue
        pos += len(p)
        para_ends.add(pos)
        pos += 1                      # the joining space

    body = _norm(text.replace("\n", " "))

    def offsets_of(units):
        out, cursor = set(), 0
        for u in units:
            u = _norm(u)
            idx = body.find(u, cursor)
            if idx < 0:
                continue
            out.add(idx)
            cursor = idx + len(u)
        return out

    return body, para_ends, offsets_of(_split_sentences(text)), offsets_of(_split_clauses(text))


def profile_cell(cell_dir, raw_by_id, label=None):
    frags = load_jsonl(Path(cell_dir) / "prose_fragments.jsonl")
    by_rec = {}
    for f in frags:
        by_rec.setdefault(f["record_id"], []).append(f)

    frags_per_doc, words_per_frag = [], []
    btype = Counter()
    deciles = Counter()
    opening = Counter()

    for rid, rows in by_rec.items():
        if rid not in raw_by_id:
            continue
        raw = raw_by_id[rid]
        body, para_ends, sent_starts, clause_starts = boundary_offsets(raw)
        frags_per_doc.append(len(rows))

        cursor = 0
        for i, row in enumerate(rows):
            t = _norm(row["text"])
            words_per_frag.append(len(t.split()))

            first = re.match(r"[A-Za-z']+", t)
            word = first.group(0).lower() if first else ""
            opening["connective" if word in CONNECTIVES else
                    "pronoun" if word in PRONOUNS else "other"] += 1

            idx = body.find(t, cursor)
            if idx < 0:
                idx = body.find(t)
            if idx < 0:
                btype["unlocatable"] += 1
                continue
            cursor = idx + len(t)

            if i == 0:                       # document start is not a chosen cut
                continue
            if any(abs(idx - p) <= 2 for p in para_ends):
                btype["paragraph"] += 1
            elif idx in sent_starts:
                btype["sentence"] += 1
            elif idx in clause_starts:
                btype["clause"] += 1
            else:
                btype["mid-clause"] += 1

            if len(body):
                deciles[min(9, int(idx / len(body) * 10))] += 1

    return {
        "label":       label or Path(cell_dir).name,
        "docs":        len(frags_per_doc),
        "fragments":   sum(frags_per_doc),
        "frags_doc":   st.mean(frags_per_doc) if frags_per_doc else 0,
        "words_frag":  st.median(words_per_frag) if words_per_frag else 0,
        "words_mean":  st.mean(words_per_frag) if words_per_frag else 0,
        "btype":       btype,
        "deciles":     deciles,
        "opening":     opening,
    }


def _pct(counter, key):
    total = sum(counter.values())
    return 100.0 * counter[key] / total if total else 0.0


def report(profiles):
    print("=" * 86)
    print(" GRANULARITY — what the strategy actually produced")
    print("=" * 86)
    print(f"{'cell':<26}{'docs':>6}{'frags':>9}{'frags/doc':>11}"
          f"{'words/frag':>12}{'median':>9}")
    for p in profiles:
        print(f"{p['label']:<26}{p['docs']:>6}{p['fragments']:>9}"
              f"{p['frags_doc']:>11.1f}{p['words_mean']:>12.1f}{p['words_frag']:>9.0f}")

    print()
    print("=" * 86)
    print(" BOUNDARY TYPE — the finest unit each cut coincides with")
    print("=" * 86)
    print(f"{'cell':<26}{'paragraph':>11}{'sentence':>11}{'clause':>10}"
          f"{'mid-clause':>13}{'unlocatable':>13}")
    for p in profiles:
        b = p["btype"]
        print(f"{p['label']:<26}{_pct(b,'paragraph'):>10.1f}%{_pct(b,'sentence'):>10.1f}%"
              f"{_pct(b,'clause'):>9.1f}%{_pct(b,'mid-clause'):>12.1f}%"
              f"{_pct(b,'unlocatable'):>12.1f}%")

    print()
    print("=" * 86)
    print(" POSITION — share of cuts by decile of document (flat = position-blind)")
    print("=" * 86)
    print(f"{'cell':<26}" + "".join(f"{d*10:>6}%" for d in range(10)))
    for p in profiles:
        total = sum(p["deciles"].values()) or 1
        print(f"{p['label']:<26}" +
              "".join(f"{100.0*p['deciles'][d]/total:>6.1f}" for d in range(10)))

    print()
    print("=" * 86)
    print(" FRAGMENT OPENINGS — dangling links left exposed to a reassembler")
    print("=" * 86)
    print(f"{'cell':<26}{'connective':>12}{'pronoun':>10}{'other':>9}"
          f"   (higher connective+pronoun = more ordering signal exposed)")
    for p in profiles:
        o = p["opening"]
        print(f"{p['label']:<26}{_pct(o,'connective'):>11.1f}%{_pct(o,'pronoun'):>9.1f}%"
              f"{_pct(o,'other'):>8.1f}%")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cell", required=True, help="cell dir with prose_fragments.jsonl")
    ap.add_argument("--compare", nargs="*", default=[],
                    help="other cell dirs to profile alongside")
    ap.add_argument("--raw", default=str(DEFAULT_RAW))
    args = ap.parse_args()

    raw_by_id = {r["record_id"]: r["text"] for r in load_jsonl(args.raw)}
    profiles = [profile_cell(c, raw_by_id) for c in [args.cell] + args.compare]
    report(profiles)


if __name__ == "__main__":
    main()
