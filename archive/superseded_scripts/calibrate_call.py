#!/usr/bin/env python3
"""
calibrate_call.py — ONE real Sonnet 5 linkage call, to ground the cost estimate.

Sends a single Game L (linkage) prompt for one pool of 100 records — the biggest,
riskiest prompt in a full run — and reports:
  * estimated vs ACTUAL input tokens   (validates the chars/token ratio)
  * estimated vs ACTUAL output tokens  (validates the grouping-output guess)
  * the correction factors to feed back into estimate_cost.py
  * whether the model produced a COHERENT grouping at this pool size, or choked

Exactly one billable call is made. Transient-failure retries are capped at 2 and
only fire on errors (which are not billed for completed output).

Fragment IDs are masked to item_N before the model sees them — the corpus uses
prose_NNNN_frag_NNN ids that encode both record and position, which would leak
the answer outright.

Usage:
    python calibrate_call.py --data ./data/prose_v4 --pool-records 100
    python calibrate_call.py --data ./data/prose_v4 --dry-run     # no API call
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
sys.path.insert(0, str(HERE.parent / "harness"))

IN_PER_M, OUT_PER_M = 2.0, 10.0
MODEL = "claude-sonnet-5"
CONTEXT_LIMIT = 200_000


def load_env_key(path=HERE / ".env"):
    if os.environ.get("API_KEY"):
        return os.environ["API_KEY"]
    if path.exists():
        for line in path.open(encoding="utf-8"):
            m = re.match(r'\s*API_KEY\s*=\s*(.*)', line)
            if m:
                return m.group(1).strip().strip('"').strip("'")
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="./data/prose_v4")
    ap.add_argument("--pool-records", type=int, default=100)
    ap.add_argument("--max-tokens", type=int, default=32000)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    d = Path(args.data)
    frs = [json.loads(l) for l in (d / "prose_fragments.jsonl").open(encoding="utf-8") if l.strip()]
    by = defaultdict(list)
    for f in frs:
        by[f["record_id"]].append(f)
    recs = sorted(by)

    # Pick the LARGEST natural pool — the worst case is what needs validating.
    pools = [recs[i:i + args.pool_records]
             for i in range(0, len(recs), args.pool_records)]
    pool = max(pools, key=lambda ch: sum(len(f["text"]) for r in ch for f in by[r]))
    pool_frags = [f for r in pool for f in by[r]]
    pool_chars = sum(len(f["text"]) for f in pool_frags)
    print(f"pool: {len(pool)} records / {len(pool_frags):,} fragments / "
          f"{pool_chars:,} chars  (largest of {len(pools)} pools)")

    # ── build prompt with MASKED ids ────────────────────────────────────────
    rng = random.Random(args.seed)
    shuffled = pool_frags[:]
    rng.shuffle(shuffled)
    alias = {f"item_{i}": f["fragment_id"] for i, f in enumerate(shuffled)}
    lines = "\n".join(f'item_{i}: {f["text"]}' for i, f in enumerate(shuffled))
    prompt = (
        f"Below are {len(shuffled)} shuffled sentences drawn from "
        f"{len(pool)} different clinical case documents.\n"
        f"Group ALL sentences into the {len(pool)} documents they came from. "
        f"Use every item exactly once. Documents vary in length.\n\n"
        f"Sentences:\n{lines}\n\n"
        f"Return ONLY a JSON array of {len(pool)} arrays of item labels. "
        f"No prose, no markdown."
    )

    est_in = pool_chars / 4 + 200
    est_out = len(pool_frags) * 3
    print(f"ESTIMATE  input ~{est_in:,.0f} tok | output ~{est_out:,.0f} tok")
    if est_in + args.max_tokens > CONTEXT_LIMIT:
        print(f"  [warn] est input + max_tokens ({est_in+args.max_tokens:,.0f}) "
              f"exceeds {CONTEXT_LIMIT:,} context limit")

    if args.dry_run:
        print("dry-run: no API call made")
        return

    key = load_env_key()
    if not key:
        sys.exit("ERROR: no API_KEY found (env or corpus_expansion/.env)")

    import anthropic
    client = anthropic.Anthropic(api_key=key)

    print(f"\ncalling {MODEL} (ONE call, max_tokens={args.max_tokens:,}) ...", flush=True)
    t0 = time.perf_counter()
    resp = None
    for attempt in range(3):
        try:
            # Streaming is REQUIRED by the SDK for requests that may exceed 10
            # minutes — a large max_tokens at this prompt size trips that guard
            # client-side (ValueError, before any request is sent / billed).
            with client.messages.stream(
                model=MODEL, max_tokens=args.max_tokens,
                messages=[{"role": "user", "content": prompt}],
            ) as stream:
                for _ in stream.text_stream:
                    pass
                resp = stream.get_final_message()
            break
        except Exception as e:
            msg = str(e)
            if attempt < 2 and any(s in msg for s in ("429", "500", "502", "503",
                                                      "529", "overloaded")):
                print(f"  transient ({msg[:60]}) — retrying", flush=True)
                time.sleep(5 * (attempt + 1))
                continue
            raise
    wall = time.perf_counter() - t0

    act_in = resp.usage.input_tokens
    act_out = resp.usage.output_tokens
    text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
    (HERE / "calibration_raw_response.txt").write_text(text, encoding="utf-8")

    # ── coherence check ─────────────────────────────────────────────────────
    verdict, groups = {}, None
    try:
        s, e = text.find("["), text.rfind("]")
        groups = json.loads(text[s:e + 1])
    except Exception as ex:
        verdict["parse"] = f"FAILED to parse JSON: {ex}"

    if groups is not None:
        flat = [x for g in groups for x in g]
        valid = set(alias)
        mapped = [[alias[x] for x in g if x in valid] for g in groups]
        true_groups = {r: [f["fragment_id"] for f in by[r]] for r in pool}
        tp = {(a, b) for ids in true_groups.values() for a, b in combinations(sorted(ids), 2)}
        gp = {(a, b) for ids in mapped for a, b in combinations(sorted(ids), 2)}
        inter = len(gp & tp)
        prec = inter / len(gp) if gp else 0.0
        rec_ = inter / len(tp) if tp else 0.0
        f1 = 2 * prec * rec_ / (prec + rec_) if prec + rec_ else 0.0
        sizes = sorted((len(g) for g in mapped), reverse=True)
        verdict.update({
            "groups_returned": len(groups),
            "groups_expected": len(pool),
            "labels_emitted": len(flat),
            "labels_expected": len(shuffled),
            "invalid_labels": len([x for x in flat if x not in valid]),
            "duplicate_labels": len(flat) - len(set(flat)),
            "missing_labels": len(valid) - len(set(x for x in flat if x in valid)),
            "largest_group": sizes[0] if sizes else 0,
            "singletons": sum(1 for s_ in sizes if s_ == 1),
            "precision": round(prec, 4), "recall": round(rec_, 4), "f1": round(f1, 4),
        })

    # ── report ──────────────────────────────────────────────────────────────
    ci, co = act_in / est_in, (act_out / est_out if est_out else 0)
    print("\n" + "=" * 74)
    print(" CALIBRATION RESULT")
    print("=" * 74)
    print(f"  wall clock            : {wall:.1f}s")
    print(f"  {'':22s} {'estimated':>12s} {'ACTUAL':>12s} {'factor':>9s}")
    print(f"  {'input tokens':22s} {est_in:12,.0f} {act_in:12,d} {ci:9.3f}")
    print(f"  {'output tokens':22s} {est_out:12,.0f} {act_out:12,d} {co:9.3f}")
    call_cost = act_in / 1e6 * IN_PER_M + act_out / 1e6 * OUT_PER_M
    print(f"  cost of THIS call     : ${call_cost:.4f}")
    print(f"\n  chars/token (real clinical text): {pool_chars/act_in:.3f}"
          f"   (estimate assumed 4.000)")
    print("\n" + "=" * 74)
    print(" COHERENCE AT 100-RECORD POOL")
    print("=" * 74)
    for k, v in verdict.items():
        print(f"  {k:20s} : {v}")
    print(f"\n  raw response saved -> calibration_raw_response.txt")
    print(f"\n  feed back:  python estimate_cost.py --data {args.data} "
          f"--cal-in {ci:.3f} --cal-out {co:.3f}")

    (HERE / "calibration_result.json").write_text(json.dumps({
        "model": MODEL, "pool_records": len(pool), "pool_fragments": len(pool_frags),
        "pool_chars": pool_chars, "est_in": est_in, "est_out": est_out,
        "actual_in": act_in, "actual_out": act_out,
        "cal_in": ci, "cal_out": co, "call_cost_usd": call_cost,
        "wall_seconds": wall, "coherence": verdict,
    }, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
