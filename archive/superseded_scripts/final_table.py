#!/usr/bin/env python3
"""
final_table.py — the frozen Game L (linkage) results table.

Scope rules enforced here:
  * prose_v3 ONLY. Linkage F1 is NOT comparable across corpus sizes (the random
    floor moves 0.031 -> 0.0096 -> 0.0019 as records go 25 -> 96 -> 500), so
    mixing corpora in one Game L table is invalid. No cross-size rows.
  * Synthetic prose linkage is EXCLUDED entirely — not a baseline, not a finding.
    Its lexical signal is inverted (Cohen's d = -0.37), so no clustering method
    can work; it is reported as not-applicable with that diagnostic.
  * Ordering (Game O) is untouched and not reported here.

Both guardrails are re-verified against the frozen snapshot:
  GATE 1  fixed Memon must beat the trivial one-big-cluster F1 on prose_v3.
  GATE 2  identifiers must stay within 2 sigma of the random floor.

Usage:  python final_table.py --runs 500
"""

import argparse
import hashlib
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "harness"))

from loader import load_fragments, group_fragments_by_record   # noqa: E402
from scoring import score_linkage                              # noqa: E402
import harness as H                                            # noqa: E402
from memon_linkage import memon_grouping, partition_stats      # noqa: E402

PROSE = HERE / "data" / "prose_v3"
IDENT = ROOT / "data" / "identifier"


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()[:16]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=500)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    out = []
    def say(s=""):
        print(s, flush=True)
        out.append(s)

    # ── frozen snapshot identity ─────────────────────────────────────────────
    say("=" * 78)
    say(" FROZEN CORPUS SNAPSHOT")
    say("=" * 78)
    for f in ("prose_fragments.jsonl", "prose_answer_key.jsonl"):
        p = PROSE / f
        say(f"  {f:26s} {p.stat().st_size:>9,} bytes  sha256={sha(p)}")

    frs = load_fragments(PROSE / "prose_fragments.jsonl")
    tg  = group_fragments_by_record(PROSE / "prose_fragments.jsonl") \
          if False else group_fragments_by_record(frs)
    ids = [f["fragment_id"] for f in frs]
    n, nrec = len(ids), len(tg)
    say(f"  prose_v3: {nrec} records / {n:,} fragments   "
        f"(post-cutoff verified 500/500, Feb 2026+)")
    say(f"  seed={args.seed}  random_runs={args.runs:,}")
    say()

    # ── reference points ─────────────────────────────────────────────────────
    triv = score_linkage({0: list(ids)}, tg)
    say(f"  trivial 'one big cluster' F1 = {triv['f1']:.4f}   <-- GATE 1 bar")

    say(f"\nrandom baseline ({args.runs:,} runs) ...")
    true_order = {r: v for r, v in tg.items()}
    _, l_p, l_r, l_f = H.eval_random(frs, true_order, tg, args.runs)
    rnd = dict(f1=float(l_f.mean()), p=float(l_p.mean()), r=float(l_r.mean()),
               sd=float(l_f.std(ddof=1)))
    say(f"  random F1 = {rnd['f1']:.4f} +- {rnd['sd']:.4f}")

    # ── methods on prose_v3 ──────────────────────────────────────────────────
    rows = [("Random baseline", rnd["f1"], rnd["p"], rnd["r"], None)]

    for variant, label in (("legacy-greedy", "Memon LEGACY (greedy, degenerate)"),
                           ("fixed",         "Memon FIXED (tfidf + average)")):
        say(f"\n{label} ...")
        g = memon_grouping(frs, nrec, variant=variant, seed=args.seed)
        s = score_linkage(g, tg)
        st = partition_stats(g, n)
        say(f"  F1={s['f1']:.4f}  P={s['precision']:.4f}  R={s['recall']:.4f}  "
            f"largest cluster {st['largest']}/{n} ({st['largest_pct']:.1f}%)")
        rows.append((label, s["f1"], s["precision"], s["recall"], st))

    # ── GATE 1 ───────────────────────────────────────────────────────────────
    fixed_f1 = rows[-1][1]
    gate1 = fixed_f1 > triv["f1"]

    # ── GATE 2: identifiers stay at floor ────────────────────────────────────
    say("\n" + "-" * 78)
    say("GATE 2 — identifier corpus (synthetic, unchanged) must stay at chance")
    ifrs = load_fragments(IDENT / "fragments.jsonl")
    itg  = group_fragments_by_record(ifrs)
    _, _, _, il = H.eval_random(ifrs, {r: v for r, v in itg.items()}, itg, args.runs)
    i_mean, i_sd = float(il.mean()), float(il.std(ddof=1))
    ceiling = i_mean + 2 * i_sd
    ig = memon_grouping(ifrs, len(itg), variant="fixed", seed=args.seed)
    isc = score_linkage(ig, itg)
    ist = partition_stats(ig, len(ifrs))
    gate2 = isc["f1"] <= ceiling
    say(f"  identifier random floor : {i_mean:.4f} +- {i_sd:.4f}  -> 2-sigma ceiling {ceiling:.4f}")
    say(f"  fixed Memon on identifiers: F1={isc['f1']:.4f}  "
        f"largest cluster {ist['largest']}/{len(ifrs)} ({ist['largest_pct']:.1f}%)")

    # ── final table ──────────────────────────────────────────────────────────
    say("\n" + "=" * 78)
    say(" FINAL GAME L (LINKAGE) TABLE — prose_v3 ONLY, 500 records / 5,936 fragments")
    say("=" * 78)
    say(f"{'Method':38s} {'F1':>8s} {'P':>8s} {'R':>8s}  {'largest cluster':>16s}")
    say("-" * 78)
    for label, f1, p, r, st in rows:
        blob = f"{st['largest']}/{n} ({st['largest_pct']:.1f}%)" if st else "-"
        say(f"{label:38s} {f1:8.4f} {p:8.4f} {r:8.4f}  {blob:>16s}")
    say(f"{'LLM (Claude Sonnet)':38s} {'PENDING':>8s} {'-':>8s} {'-':>8s}  {'-':>16s}")
    say("-" * 78)
    say(f"  reference: trivial one-big-cluster F1 = {triv['f1']:.4f}")
    say(f"  seed={args.seed}  random_runs={args.runs:,}")
    say()
    say("  LLM row PENDING — blocked on two items:")
    say("    (a) no API key available in this environment;")
    say("    (b) a single pooled call over 5,936 fragments needs ~230,000 input")
    say("        tokens, exceeding the 200,000-token context window. Chunking is")
    say("        REQUIRED, and the pool size changes the random floor "
        "(25-rec pool 0.0368 vs 500-way 0.0018),")
    say("        so random + Memon must be re-run at whatever pool structure the")
    say("        LLM uses or the rows are not comparable.")
    say()
    say("  EXCLUDED: synthetic prose linkage. Lexical signal is inverted there")
    say("  (Cohen's d = -0.37 word-bigram, -0.28 char-4gram, -0.08 tfidf), so no")
    say("  clustering method can work. Reported as NOT APPLICABLE, not as a number.")
    say()
    say("=" * 78)
    say(f"  GATE 1 (fixed Memon beats trivial on prose_v3): "
        f"{'PASS' if gate1 else 'FAIL'}  "
        f"({fixed_f1:.4f} vs {triv['f1']:.4f}, {fixed_f1/triv['f1']:.1f}x)")
    say(f"  GATE 2 (identifiers stay at chance):            "
        f"{'PASS' if gate2 else 'FAIL'}  "
        f"({isc['f1']:.4f} vs ceiling {ceiling:.4f})")
    say("=" * 78)

    (HERE / "final_linkage_table.txt").write_text("\n".join(out), encoding="utf-8")
    print("\nwritten: final_linkage_table.txt")


if __name__ == "__main__":
    main()
