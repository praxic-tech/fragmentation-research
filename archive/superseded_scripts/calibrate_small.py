#!/usr/bin/env python3
"""
calibrate_small.py — TWO small Sonnet 5 calls to ground the cost estimate.

  CALL 1  Ordering (Game O) on ONE document of ~average length.
          Calibrates the chars/token ratio on real clinical text and the
          ordering-output guess. Ordering is ~70% of a full run's cost.
  CALL 2  Linkage (Game L) on a SMALL pool of average-length documents.
          Calibrates the linkage-output guess (billed 5x) and tests whether
          the model produces a coherent grouping at all.

Deliberately small: together roughly $0.04, versus ~$0.36 for a single
100-record pool. Coherence at this pool size is a lower bound — it does not
prove a 100-record pool works, only that the approach is sound at small scale.

Fragment ids are masked to item_N before the model sees them (the corpus ids
prose_NNNN_frag_NNN encode record AND position, which would leak the answer).

Usage:
    python calibrate_small.py --data ./data/prose_v4 --pool-docs 10
    python calibrate_small.py --data ./data/prose_v4 --dry-run
"""

import argparse
import json
import os
import random
import re
import sys
import time
from collections import defaultdict
from itertools import combinations
from pathlib import Path

HERE = Path(__file__).resolve().parent
IN_PER_M, OUT_PER_M = 2.0, 10.0
MODEL = "claude-sonnet-5"


def load_key():
    if os.environ.get("API_KEY"):
        return os.environ["API_KEY"]
    p = HERE / ".env"
    if p.exists():
        for line in p.open(encoding="utf-8"):
            m = re.match(r'\s*API_KEY\s*=\s*(.*)', line)
            if m:
                return m.group(1).strip().strip('"').strip("'")
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="./data/prose_v4")
    ap.add_argument("--pool-docs", type=int, default=10)
    ap.add_argument("--ord-tokens", type=int, default=4000)
    ap.add_argument("--lnk-tokens", type=int, default=32000,
                    help="linkage output budget; 8000 was exhausted by reasoning "
                         "before any answer was emitted")
    ap.add_argument("--skip-ordering", action="store_true",
                    help="only re-run the linkage call (ordering already calibrated)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    d = Path(args.data)
    frs = [json.loads(l) for l in (d / "prose_fragments.jsonl").open(encoding="utf-8") if l.strip()]
    by = defaultdict(list)
    for f in frs:
        by[f["record_id"]].append(f)
    recs = sorted(by)

    # median fragment count -> "average length"
    counts = sorted(len(by[r]) for r in recs)
    median_n = counts[len(counts) // 2]
    ranked = sorted(recs, key=lambda r: abs(len(by[r]) - median_n))
    doc = ranked[0]                       # closest to median length
    pool = ranked[:args.pool_docs]        # the N most average-length documents

    doc_frags = by[doc]
    doc_chars = sum(len(f["text"]) for f in doc_frags)
    pool_frags = [f for r in pool for f in by[r]]
    pool_chars = sum(len(f["text"]) for f in pool_frags)

    print(f"corpus median fragments/doc = {median_n}")
    print(f"CALL 1 ordering : {doc} — {len(doc_frags)} frags / {doc_chars:,} chars")
    print(f"CALL 2 linkage  : {len(pool)} docs / {len(pool_frags)} frags / {pool_chars:,} chars")

    est1_in, est1_out = doc_chars / 4 + 150, len(doc_frags) * 15
    est2_in, est2_out = pool_chars / 4 + 200, len(pool_frags) * 3
    print(f"\nESTIMATE call1  in ~{est1_in:,.0f}  out ~{est1_out:,.0f}")
    print(f"ESTIMATE call2  in ~{est2_in:,.0f}  out ~{est2_out:,.0f}")
    est_cost = ((est1_in + est2_in) / 1e6 * IN_PER_M
                + (est1_out + est2_out) / 1e6 * OUT_PER_M)
    print(f"ESTIMATE total cost of both calls: ${est_cost:.4f}")

    if args.dry_run:
        print("\ndry-run: no API calls made")
        return

    key = load_key()
    if not key:
        sys.exit("ERROR: no API_KEY found")
    import anthropic
    client = anthropic.Anthropic(api_key=key)
    rng = random.Random(args.seed)

    def call(prompt, max_tokens, label):
        print(f"\ncalling {MODEL} — {label} (max_tokens={max_tokens:,}) ...", flush=True)
        t0 = time.perf_counter()
        # The SDK refuses non-streaming requests whose max_tokens implies a
        # possible >10-minute generation (raises ValueError client-side, before
        # anything is sent or billed). Stream above that threshold.
        if max_tokens > 8192:
            with client.messages.stream(
                model=MODEL, max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
            ) as stream:
                for _ in stream.text_stream:
                    pass
                r = stream.get_final_message()
        else:
            r = client.messages.create(model=MODEL, max_tokens=max_tokens,
                                       messages=[{"role": "user", "content": prompt}])
        txt = "".join(b.text for b in r.content if getattr(b, "type", "") == "text")
        # DIAGNOSTICS the first calibration lacked. Without stop_reason and the
        # per-block type breakdown we could not tell "budget starved" from "model
        # choked" — which is exactly why the linkage verdict came back inconclusive.
        blocks = [(getattr(b, "type", "?"),
                   len(getattr(b, "text", None) or getattr(b, "thinking", None) or ""))
                  for b in r.content]
        diag = {"stop_reason": r.stop_reason, "blocks": blocks,
                "n_blocks": len(r.content), "text_chars": len(txt)}
        print(f"    stop_reason={r.stop_reason}  blocks={blocks}", flush=True)
        return r.usage.input_tokens, r.usage.output_tokens, txt, time.perf_counter() - t0, diag

    # ── CALL 1: ordering ────────────────────────────────────────────────────
    sh = doc_frags[:]
    rng.shuffle(sh)
    alias1 = {f"item_{i}": f["fragment_id"] for i, f in enumerate(sh)}
    lines = "\n".join(f'item_{i}: {f["text"]}' for i, f in enumerate(sh))
    p1 = ("These sentences come from ONE clinical case document, shuffled. "
          "Put them back in their most likely original order.\n\nSentences:\n"
          + lines + "\n\nReturn ONLY a JSON array of the item labels in order.")
    if args.skip_ordering:
        a1_in, a1_out, t1, w1 = 1674, 830, '["cached"]', 0.0
        d1 = {"stop_reason": "cached-from-previous-run", "blocks": [], "n_blocks": 0,
              "text_chars": 0}
        print("\nCALL1 ordering: SKIPPED (already calibrated: 1,674 in / 830 out)")
    else:
        a1_in, a1_out, t1, w1, d1 = call(p1, args.ord_tokens, "ordering, 1 doc")

    # ── CALL 2: linkage ─────────────────────────────────────────────────────
    sh2 = pool_frags[:]
    rng.shuffle(sh2)
    alias2 = {f"item_{i}": f["fragment_id"] for i, f in enumerate(sh2)}
    lines2 = "\n".join(f'item_{i}: {f["text"]}' for i, f in enumerate(sh2))
    p2 = (f"Below are {len(sh2)} shuffled sentences from {len(pool)} different "
          f"clinical case documents.\nGroup ALL sentences into the {len(pool)} "
          f"documents they came from. Use every item exactly once. "
          f"Documents vary in length.\n\nSentences:\n" + lines2 +
          f"\n\nReturn ONLY a JSON array of {len(pool)} arrays of item labels.")
    a2_in, a2_out, t2, w2, d2 = call(p2, args.lnk_tokens, f"linkage, {len(pool)}-doc pool")

    # ── scoring ─────────────────────────────────────────────────────────────
    def parse(txt):
        s, e = txt.find("["), txt.rfind("]")
        return json.loads(txt[s:e + 1])

    ord_ok = {}
    try:
        g = parse(t1)
        got = [alias1.get(x, x) for x in g]
        truth = [f["fragment_id"] for f in sorted(doc_frags, key=lambda f: f["fragment_id"])]
        from scipy.stats import kendalltau
        if sorted(got) == sorted(truth):
            rank = {f: i for i, f in enumerate(truth)}
            tau = kendalltau([rank[x] for x in got], list(range(len(truth)))).statistic
            ord_ok = {"valid_permutation": True, "kendall_tau": round(float(tau), 4)}
        else:
            ord_ok = {"valid_permutation": False,
                      "returned": len(got), "expected": len(truth)}
    except Exception as ex:
        ord_ok = {"parse_error": str(ex)[:120]}

    lnk = {}
    try:
        g2 = parse(t2)
        mapped = [[alias2[x] for x in grp if x in alias2] for grp in g2]
        flat = [x for grp in g2 for x in grp]
        tg = {r: [f["fragment_id"] for f in by[r]] for r in pool}
        tp = {(a, b) for ids in tg.values() for a, b in combinations(sorted(ids), 2)}
        gp = {(a, b) for ids in mapped for a, b in combinations(sorted(ids), 2)}
        inter = len(gp & tp)
        prec = inter / len(gp) if gp else 0.0
        rec_ = inter / len(tp) if tp else 0.0
        sizes = sorted((len(x) for x in mapped), reverse=True)
        lnk = {"groups_returned": len(g2), "groups_expected": len(pool),
               "labels_emitted": len(flat), "labels_expected": len(sh2),
               "invalid": len([x for x in flat if x not in alias2]),
               "duplicates": len(flat) - len(set(flat)),
               "missing": len(alias2) - len({x for x in flat if x in alias2}),
               "largest_group": sizes[0] if sizes else 0,
               "precision": round(prec, 4), "recall": round(rec_, 4),
               "f1": round(2 * prec * rec_ / (prec + rec_), 4) if prec + rec_ else 0.0}
    except Exception as ex:
        lnk = {"parse_error": str(ex)[:120]}

    c1 = a1_in / 1e6 * IN_PER_M + a1_out / 1e6 * OUT_PER_M
    c2 = a2_in / 1e6 * IN_PER_M + a2_out / 1e6 * OUT_PER_M
    ci1, co1 = a1_in / est1_in, (a1_out / est1_out if est1_out else 0)
    ci2, co2 = a2_in / est2_in, (a2_out / est2_out if est2_out else 0)

    print("\n" + "=" * 76)
    print(" CALIBRATION — estimated vs ACTUAL")
    print("=" * 76)
    print(f"{'':26s} {'estimated':>11s} {'ACTUAL':>10s} {'factor':>9s}")
    print(f"  {'CALL1 ordering input':24s} {est1_in:11,.0f} {a1_in:10,d} {ci1:9.3f}")
    print(f"  {'CALL1 ordering output':24s} {est1_out:11,.0f} {a1_out:10,d} {co1:9.3f}")
    print(f"  {'CALL2 linkage input':24s} {est2_in:11,.0f} {a2_in:10,d} {ci2:9.3f}")
    print(f"  {'CALL2 linkage output':24s} {est2_out:11,.0f} {a2_out:10,d} {co2:9.3f}")
    print(f"\n  chars/token (real clinical text): "
          f"ordering {doc_chars/a1_in:.3f} | linkage {pool_chars/a2_in:.3f}"
          f"   (estimate assumed 4.000)")
    print(f"  actual cost of these two calls: ${c1+c2:.4f}  "
          f"(est ${est_cost:.4f})")
    print(f"  wall clock: ordering {w1:.1f}s | linkage {w2:.1f}s")
    print("\n" + "=" * 76)
    print(" COHERENCE")
    print("=" * 76)
    print(f"  ordering : {ord_ok}")
    print(f"  call2 stop_reason : {d2['stop_reason']}")
    print(f"  call2 blocks      : {d2['blocks']}")
    print(f"  linkage  : {lnk}")
    print(f"\n  feed back: python estimate_cost.py --data {args.data} "
          f"--cal-in {(ci1+ci2)/2:.3f} --cal-out {(co1+co2)/2:.3f}")

    (HERE / "calibration_small.json").write_text(json.dumps({
        "model": MODEL, "doc": doc, "doc_frags": len(doc_frags), "doc_chars": doc_chars,
        "pool_docs": len(pool), "pool_frags": len(pool_frags), "pool_chars": pool_chars,
        "est": {"o_in": est1_in, "o_out": est1_out, "l_in": est2_in, "l_out": est2_out},
        "actual": {"o_in": a1_in, "o_out": a1_out, "l_in": a2_in, "l_out": a2_out},
        "factors": {"o_in": ci1, "o_out": co1, "l_in": ci2, "l_out": co2},
        "cost_usd": c1 + c2, "ordering": ord_ok, "linkage": lnk,
        "diagnostics": {"call1": d1, "call2": d2},
    }, indent=2), encoding="utf-8")
    (HERE / "calibration_small_raw.txt").write_text(
        f"=== CALL1 ordering ===\n{t1}\n\n=== CALL2 linkage ===\n{t2}", encoding="utf-8")
    print("  saved: calibration_small.json, calibration_small_raw.txt")


if __name__ == "__main__":
    main()
