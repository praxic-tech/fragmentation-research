#!/usr/bin/env python3
"""
bench_reasoning.py — does Game L linkage hold up with less reasoning?

Thinking tokens were 97% of the calibration call's billed output (25,021 of
25,923) and 71% of a projected full run's cost, so this sweeps reasoning depth
on the SAME 10-document pool and compares F1 against the full-reasoning baseline.

IMPORTANT — the knob is `effort`, not `budget_tokens`:
  `thinking: {"type": "enabled", "budget_tokens": N}` is REMOVED on Sonnet 5 and
  returns a 400. The replacement is `output_config: {"effort": ...}` with
  adaptive thinking. There is no way to request "about 2,000 thinking tokens".
  Also note omitting `thinking` entirely runs ADAPTIVE on Sonnet 5 (it is on by
  default), which is what the baseline run did.

Settings swept:
  off   — thinking: {"type": "disabled"}                 (no reasoning at all)
  low   — thinking adaptive + output_config.effort=low
  medium— thinking adaptive + output_config.effort=medium
  (baseline: adaptive at the default effort — cited from calibration_small.json,
   NOT re-run, so the comparison costs nothing extra.)

Same pool, same seed, same masked ids as the calibration call, so F1 numbers are
directly comparable.

Usage:
    python bench_reasoning.py --settings off,low
    python bench_reasoning.py --dry-run
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

# Baseline from the earlier calibration call (full/default reasoning) — cited,
# not re-run. See calibration_small.json.
BASELINE = {"name": "baseline (adaptive, default effort)", "in": 15054,
            "out": 25923, "f1": 0.7160, "p": 0.7302, "r": 0.7024,
            "text_chars": 3158, "wall": 251.3}

# Reference points for the 10-doc pool (computed in earlier steps).
RANDOM_FLOOR = 0.0967
TRIVIAL = 0.1765


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


def build_pool(data, pool_docs, seed):
    """Rebuild the EXACT pool the calibration call used."""
    d = Path(data)
    frs = [json.loads(l) for l in (d / "prose_fragments.jsonl").open(encoding="utf-8") if l.strip()]
    by = defaultdict(list)
    for f in frs:
        by[f["record_id"]].append(f)
    recs = sorted(by)
    counts = sorted(len(by[r]) for r in recs)
    median_n = counts[len(counts) // 2]
    pool = sorted(recs, key=lambda r: abs(len(by[r]) - median_n))[:pool_docs]
    pool_frags = [f for r in pool for f in by[r]]

    rng = random.Random(seed)
    sh = pool_frags[:]
    rng.shuffle(sh)
    alias = {f"item_{i}": f["fragment_id"] for i, f in enumerate(sh)}
    lines = "\n".join(f'item_{i}: {f["text"]}' for i, f in enumerate(sh))
    prompt = (f"Below are {len(sh)} shuffled sentences from {len(pool)} different "
              f"clinical case documents.\nGroup ALL sentences into the {len(pool)} "
              f"documents they came from. Use every item exactly once. "
              f"Documents vary in length.\n\nSentences:\n" + lines +
              f"\n\nReturn ONLY a JSON array of {len(pool)} arrays of item labels.")
    true_groups = {r: [f["fragment_id"] for f in by[r]] for r in pool}
    return prompt, alias, true_groups, pool, pool_frags


def score(text, alias, true_groups):
    out = {}
    try:
        s, e = text.find("["), text.rfind("]")
        groups = json.loads(text[s:e + 1])
    except Exception as ex:
        return {"parse_error": str(ex)[:100]}
    mapped = [[alias[x] for x in g if x in alias] for g in groups]
    flat = [x for g in groups for x in g]
    tp = {(a, b) for ids in true_groups.values() for a, b in combinations(sorted(ids), 2)}
    gp = {(a, b) for ids in mapped for a, b in combinations(sorted(ids), 2)}
    inter = len(gp & tp)
    p = inter / len(gp) if gp else 0.0
    r = inter / len(tp) if tp else 0.0
    out.update({
        "groups": len(groups), "labels": len(flat), "expected_labels": len(alias),
        "invalid": len([x for x in flat if x not in alias]),
        "duplicates": len(flat) - len(set(flat)),
        "missing": len(alias) - len({x for x in flat if x in alias}),
        "precision": round(p, 4), "recall": round(r, 4),
        "f1": round(2 * p * r / (p + r), 4) if p + r else 0.0,
    })
    return out


# Sonnet 5 accepts adaptive or disabled thinking; budget_tokens is a 400.
SETTINGS = {
    "off":    {"thinking": {"type": "disabled"}},
    "low":    {"thinking": {"type": "adaptive"}, "output_config": {"effort": "low"}},
    "medium": {"thinking": {"type": "adaptive"}, "output_config": {"effort": "medium"}},
    "high":   {"thinking": {"type": "adaptive"}, "output_config": {"effort": "high"}},
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="./data/prose_v4")
    ap.add_argument("--pool-docs", type=int, default=10)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--max-tokens", type=int, default=32000)
    ap.add_argument("--settings", default="off,low",
                    help="comma-separated subset of: off,low,medium,high")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    prompt, alias, true_groups, pool, pool_frags = build_pool(
        args.data, args.pool_docs, args.seed)
    print(f"pool: {len(pool)} docs / {len(pool_frags)} fragments "
          f"(same pool + seed as the calibration call)")
    print(f"reference: random floor F1={RANDOM_FLOOR:.4f} | trivial F1={TRIVIAL:.4f}")
    print(f"baseline : F1={BASELINE['f1']:.4f} at {BASELINE['out']:,} output tokens\n")

    want = [s.strip() for s in args.settings.split(",") if s.strip()]
    for s in want:
        if s not in SETTINGS:
            sys.exit(f"unknown setting {s!r}; choose from {list(SETTINGS)}")

    if args.dry_run:
        for s in want:
            print(f"  would call {MODEL} with {json.dumps(SETTINGS[s])}")
        print("dry-run: no API calls made")
        return

    key = load_key()
    if not key:
        sys.exit("ERROR: no API_KEY found")
    import anthropic
    client = anthropic.Anthropic(api_key=key)

    rows, total_cost = [], 0.0
    for name in want:
        cfg = SETTINGS[name]
        print(f"--- {name}: {json.dumps(cfg)} ---", flush=True)
        kwargs = dict(model=MODEL, max_tokens=args.max_tokens,
                      messages=[{"role": "user", "content": prompt}], **cfg)
        t0 = time.perf_counter()
        try:
            if args.max_tokens > 8192:
                with client.messages.stream(**kwargs) as st:
                    for _ in st.text_stream:
                        pass
                    resp = st.get_final_message()
            else:
                resp = client.messages.create(**kwargs)
        except Exception as ex:
            print(f"    FAILED: {type(ex).__name__}: {str(ex)[:200]}\n", flush=True)
            rows.append({"setting": name, "error": f"{type(ex).__name__}: {str(ex)[:160]}"})
            continue
        wall = time.perf_counter() - t0

        txt = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
        blocks = [(getattr(b, "type", "?"), len(getattr(b, "text", None) or "")) for b in resp.content]
        a_in, a_out = resp.usage.input_tokens, resp.usage.output_tokens
        answer_tok = len(txt) / 3.5
        thinking_tok = max(0.0, a_out - answer_tok)
        cost = a_in / 1e6 * IN_PER_M + a_out / 1e6 * OUT_PER_M
        total_cost += cost
        sc = score(txt, alias, true_groups)
        print(f"    stop={resp.stop_reason} blocks={blocks}")
        print(f"    in={a_in:,} out={a_out:,} (answer~{answer_tok:,.0f}, "
              f"thinking~{thinking_tok:,.0f}) ${cost:.4f} {wall:.0f}s")
        print(f"    {sc}\n", flush=True)
        rows.append({"setting": name, "config": cfg, "stop_reason": resp.stop_reason,
                     "blocks": blocks, "in": a_in, "out": a_out,
                     "answer_tokens": round(answer_tok), "thinking_tokens": round(thinking_tok),
                     "cost_usd": round(cost, 4), "wall_seconds": round(wall, 1), **sc})

    # ── comparison table ────────────────────────────────────────────────────
    print("=" * 100)
    print(" REASONING BUDGET vs LINKAGE QUALITY — same 10-doc pool")
    print("=" * 100)
    print(f"{'setting':22s} {'F1':>7s} {'P':>7s} {'R':>7s} {'out tok':>9s} "
          f"{'think':>8s} {'answer':>7s} {'$':>8s} {'sec':>6s}  partition")
    print("-" * 100)
    b = BASELINE
    b_think = b["out"] - b["text_chars"] / 3.5
    print(f"{b['name']:22s} {b['f1']:7.4f} {b['p']:7.4f} {b['r']:7.4f} {b['out']:9,d} "
          f"{b_think:8,.0f} {b['text_chars']/3.5:7,.0f} "
          f"{b['in']/1e6*IN_PER_M + b['out']/1e6*OUT_PER_M:8.4f} {b['wall']:6.0f}  "
          f"280/280 clean")
    for r in rows:
        if "error" in r:
            print(f"{r['setting']:22s} {'ERROR':>7s}  {r['error']}")
            continue
        part = (f"{r.get('labels','?')}/{r.get('expected_labels','?')}"
                f"{' clean' if r.get('invalid')==0 and r.get('duplicates')==0 and r.get('missing')==0 else ' DIRTY'}"
                if "parse_error" not in r else "PARSE FAIL")
        print(f"{r['setting']:22s} {r.get('f1',0):7.4f} {r.get('precision',0):7.4f} "
              f"{r.get('recall',0):7.4f} {r['out']:9,d} {r['thinking_tokens']:8,d} "
              f"{r['answer_tokens']:7,d} {r['cost_usd']:8.4f} {r['wall_seconds']:6.0f}  {part}")
    print("-" * 100)
    print(f"  random floor F1 = {RANDOM_FLOOR:.4f} | trivial one-cluster F1 = {TRIVIAL:.4f}")
    print(f"  actual spend on this test: ${total_cost:.4f}")

    (HERE / "reasoning_sweep.json").write_text(
        json.dumps({"baseline": BASELINE, "random_floor": RANDOM_FLOOR,
                    "trivial": TRIVIAL, "runs": rows,
                    "total_cost_usd": round(total_cost, 4)}, indent=2),
        encoding="utf-8")
    print("  saved: reasoning_sweep.json")


if __name__ == "__main__":
    main()
