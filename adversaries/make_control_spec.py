"""
make_control_spec.py — build the step-1 control batch: the gate for the whole run.

Step 1 is a POSITIVE control, not a sanity check. It runs the same pools twice,
once with fragment IDs deliberately UNMASKED and once masked, and the outcome is
read from the GAP between them:

    unmasked        masked          means
    near-perfect    much lower      masking works; the gap is a paper figure
    near-perfect    near-perfect    something still leaks. STOP. Every number
                                    in the experiment is worthless.
    not near-perfect      -         the test itself is broken; you did not leak
                                    what you thought you were leaking

Without the unmasked arm, a masked arm scoring low tells you nothing: it could
mean masking works, or it could mean scoring is broken and everything scores low.

It also sends 100 document openings and asks for continuations. These are PMC
case reports published after the model's training cutoff, so the continuations
should fail. If they succeed, a high reassembly score could be memorisation
rather than reconstruction.

BUG 12 HAD TO BE FIXED BEFORE THIS COULD RUN. Ordering used to leak through the
presentation order regardless of masking, so both arms would have come back
near-perfect — row 2 of that table — and we would have read a WORKING masker as
a broken one and stopped the run for nothing.

    python adversaries/make_control_spec.py --out runs/step1_controls.json
    python adversaries/batch_submit.py --spec runs/step1_controls.json --dry-run
"""

import argparse
import json
import os
import random
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(BASE_DIR)
sys.path.insert(0, os.path.join(ROOT, "harness"))

from masking import mask_fragment_ids

DEFAULT_POOLS = os.path.join(ROOT, "data", "pools", "pools.json")
DEFAULT_FRAGMENTS = os.path.join(ROOT, "data", "prose", "prose_fragments.jsonl")
DEFAULT_RAW = os.path.join(ROOT, "data", "prose", "prose_raw.jsonl")
DEFAULT_OUT = os.path.join(ROOT, "runs", "step1_controls.json")

N_CONTROL_POOLS = 2
N_MEMORISATION_PROBES = 100
OPENING_WORDS = 60
SEED = 42


def load_jsonl(path):
    with open(path, "r", encoding="utf-8") as fh:
        return [json.loads(l) for l in fh if l.strip()]


def order_prompt(items):
    lines = "\n".join(f"{label}: {text}" for label, text in items)
    return (
        "These fragments are pieces of ONE record, shuffled. "
        "Put them back in their most likely original order.\n\n"
        "Fragments:\n" + lines +
        "\n\nReturn ONLY a JSON array of the item labels in your best order."
    )


def linkage_prompt(items, n_records):
    lines = "\n".join(f"{label}: {text}" for label, text in items)
    return (
        f"Below are {len(items)} shuffled fragments from {n_records} different "
        "records. Group them so that each group holds the fragments belonging to "
        "one record.\n\n"
        "Fragments:\n" + lines +
        f"\n\nReturn ONLY a JSON array of {n_records} arrays of item labels."
    )


def continuation_prompt(opening):
    return (
        "The following is the opening of a published clinical case report. "
        "Continue it for roughly 150 words, in the same style.\n\n"
        + opening +
        "\n\nReturn ONLY the continuation as a JSON array with a single string."
    )


def build(pools_path, fragments_path, raw_path, seed):
    pools = json.load(open(pools_path, encoding="utf-8"))["pools"]
    frags = load_jsonl(fragments_path)
    by_record = {}
    for f in frags:
        by_record.setdefault(f["record_id"], []).append(f)

    rng = random.Random(seed)
    chosen = pools[:N_CONTROL_POOLS]          # first two, deterministic, not sampled
    requests = []

    for pool in chosen:
        pid = pool["pool_id"]
        pool_frags = [f for rid in pool["members"] for f in by_record[rid]]

        # ── Game O, per document, both arms on the SAME documents ────────────
        for rid in pool["members"]:
            docf = by_record[rid]

            # unmasked: real ids, presented in true order. This is the leak we
            # are deliberately reproducing, and it should score near 1.0.
            raw_items = [(f["fragment_id"], f["text"]) for f in docf]
            requests.append({
                "cell": "ctrl-unmasked", "game": "O", "unit": rid,
                "unmasked_control": True,
                "prompt": order_prompt(raw_items),
            })

            # masked: permuted labels AND shuffled presentation (bug 12).
            masked, _ = mask_fragment_ids(docf, seed=seed)
            shown = list(masked)
            rng.shuffle(shown)
            requests.append({
                "cell": "ctrl-masked", "game": "O", "unit": rid,
                "prompt": order_prompt([(m["fragment_id"], m["text"]) for m in shown]),
            })

        # ── Game L, per pool, both arms ──────────────────────────────────────
        raw_items = [(f["fragment_id"], f["text"]) for f in pool_frags]
        rng.shuffle(raw_items)
        requests.append({
            "cell": "ctrl-unmasked", "game": "L", "unit": pid,
            "unmasked_control": True,
            "prompt": linkage_prompt(raw_items, len(pool["members"])),
        })

        masked, _ = mask_fragment_ids(pool_frags, seed=seed)
        shown = list(masked)
        rng.shuffle(shown)
        requests.append({
            "cell": "ctrl-masked", "game": "L", "unit": pid,
            "prompt": linkage_prompt(
                [(m["fragment_id"], m["text"]) for m in shown], len(pool["members"])),
        })

    # ── memorisation probe ───────────────────────────────────────────────────
    # Openings are raw document text, not fragment ids, so there is nothing for
    # preflight to catch — but they are not a masking control either. Distinct
    # cell name so they can never be averaged into the masking comparison.
    raws = load_jsonl(raw_path)
    for rec in rng.sample(raws, min(N_MEMORISATION_PROBES, len(raws))):
        opening = " ".join(rec["text"].split()[:OPENING_WORDS])
        requests.append({
            "cell": "ctrl-memorisation", "game": "O", "unit": rec["record_id"],
            "max_tokens": 512,
            "prompt": continuation_prompt(opening),
        })

    return {
        "tag": "step1_controls",
        "model": "claude-sonnet-5",
        "max_tokens": 8192,
        "seed": seed,
        "control_pools": [p["pool_id"] for p in chosen],
        "requests": requests,
    }


def parse_args():
    ap = argparse.ArgumentParser(description="Build the step-1 control batch spec.")
    ap.add_argument("--pools", default=DEFAULT_POOLS)
    ap.add_argument("--fragments", default=DEFAULT_FRAGMENTS)
    ap.add_argument("--raw", default=DEFAULT_RAW)
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--seed", type=int, default=SEED)
    return ap.parse_args()


def main():
    args = parse_args()
    spec = build(args.pools, args.fragments, args.raw, args.seed)

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(spec, fh, indent=2)

    counts = {}
    for r in spec["requests"]:
        counts[f"{r['cell']} {r['game']}"] = counts.get(f"{r['cell']} {r['game']}", 0) + 1
    print(f"pools     : {', '.join(spec['control_pools'])}")
    for k in sorted(counts):
        print(f"  {k:<24} {counts[k]:>4}")
    print(f"total     : {len(spec['requests'])} requests")
    print(f"wrote     : {args.out}")
    print("\nnext: python adversaries/batch_submit.py --spec "
          f"{os.path.relpath(args.out, ROOT)} --dry-run")


if __name__ == "__main__":
    main()
