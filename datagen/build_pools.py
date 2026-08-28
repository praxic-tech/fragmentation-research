"""
build_pools.py — the fixed sampling frame for the whole experiment.

Builds, once, and writes to data/pools/:

    pools.json          71 pools of 7 documents, the Game L sampling frame
    linkage_grid.json   the 25 pools the linkage grid runs on
    ordering_grid.json  the 180 documents the ordering grid runs on, cap 30
    manifest.json       seed, corpus fingerprint, counts, timestamp

WHY THIS IS BUILT ONCE AND NEVER REGENERATED
--------------------------------------------
Every linkage comparison in the grid is a comparison of the SAME pools cut two
different ways. If the partition is rebuilt between cells, the same documents
stop co-occurring, each cell is scored against a different set of true pairs,
and the comparison silently becomes meaningless — nothing errors, the numbers
just stop being about the strategy. So this script refuses to overwrite an
existing partition without --force, and records a fingerprint of the answer key
it was built from so a corpus change is caught rather than absorbed.

The partition ships with the paper.

WHY POOLS OF 7
--------------
Game L cannot be asked in one shot: 10 documents in a single pool already failed
at >48,000 output tokens. Pool size also sets the random floor, which is why it
never varies across the grid — Arafat's pools-of-5 run reported F1 0.22, which
looked like signal until you notice the floor at pools of 5 is ~0.20. Fixing the
pool size everywhere is what stops that recurring.

WHY 71 POOLS AND NOT 10
-----------------------
Each pool is one independent observation. Measured on this corpus, per-pool F1
ranges 0.229 to 0.703 and each pool's own trivial floor ranges 0.251 to 0.503 —
pools are not interchangeable and the floor is not a constant. SEM over 71 pools
is 0.0096; over 10 it would be 0.0256, 2.7x wider, and any grid difference under
~0.05 becomes undetectable. The pools are the sample size.

THE FLOOR IS WRITTEN PER POOL, NOT ASSUMED
------------------------------------------
Each pool carries the F1 that "put all 7 documents in one bucket" achieves on
that pool, computed from that pool's actual fragment counts. An F1 with no floor
beside it is uninterpretable: 0.05 is excellent at 500-way and worthless at
7-way. harness/scoring.py has trivial_floor() for the live path; this writes the
same quantity to disk so the grid can report a margin without recomputing it.

Usage:
    python datagen/build_pools.py                  # build (refuses to clobber)
    python datagen/build_pools.py --force          # rebuild from scratch
    python datagen/build_pools.py --verify         # check what is on disk
"""

import argparse
import hashlib
import json
import os
import random
from datetime import datetime, timezone

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(BASE_DIR)
DEFAULT_KEY = os.path.join(ROOT, "data", "prose", "prose_answer_key.jsonl")
DEFAULT_OUT = os.path.join(ROOT, "data", "pools")

# Fixed by design. See the module docstring before changing any of these.
POOL_SIZE = 7
N_LINKAGE_POOLS = 25
N_ORDERING_DOCS = 180
ORDERING_FRAGMENT_CAP = 30
SEED = 42

# Length bands from RUN_PLAN section 3, in fragments. The ordering selection is
# stratified across these so the document-length covariate survives sampling.
BANDS = [("5-15", 1, 15), ("16-30", 16, 30), ("31-60", 31, 60), ("61+", 61, 10 ** 9)]


def band_of(n):
    for name, lo, hi in BANDS:
        if lo <= n <= hi:
            return name
    raise ValueError(f"no band for {n} fragments")


def load_key(path):
    """record_id -> fragment count, in file order."""
    counts = {}
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            row = json.loads(line)
            counts[row["record_id"]] = len(row["order"])
    return counts


def fingerprint(path):
    """SHA-256 of the answer key. If this changes, the partition is stale."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def trivial_floor(sizes):
    """F1 of putting every fragment in the pool into ONE bucket.

    Recall is 1.0 by construction (every true pair is inside the single bucket),
    so precision is true_pairs / all_pairs and F1 collapses to 2p / (p + 1).
    """
    n = sum(sizes)
    if n < 2:
        return {"precision": 0.0, "recall": 1.0, "f1": 0.0}
    true_pairs = sum(s * (s - 1) // 2 for s in sizes)
    all_pairs = n * (n - 1) // 2
    p = true_pairs / all_pairs
    return {"precision": p, "recall": 1.0, "f1": 2 * p / (p + 1.0)}


def build_pools(counts, rng):
    """Shuffle all documents, then deal them into consecutive pools of 7.

    Random assignment, not stratified: pools are meant to be exchangeable draws
    from the corpus, and the per-pool floor spread that makes 71 pools necessary
    is a property we want to MEASURE, not one to engineer away by balancing.
    500 is not divisible by 7, so 71 pools use 497 documents and 3 are held out.
    Held-out ids are written to the manifest rather than dropped silently.
    """
    ids = sorted(counts)
    rng.shuffle(ids)

    n_pools = len(ids) // POOL_SIZE
    pools = []
    for i in range(n_pools):
        members = sorted(ids[i * POOL_SIZE:(i + 1) * POOL_SIZE])
        sizes = [counts[m] for m in members]
        pools.append({
            "pool_id": f"pool_{i:03d}",
            "members": members,
            "fragment_counts": sizes,
            "n_fragments": sum(sizes),
            "trivial_floor": trivial_floor(sizes),
        })
    return pools, sorted(ids[n_pools * POOL_SIZE:])


def select_ordering_docs(counts, rng):
    """180 documents for the ordering grid, stratified across length bands.

    Proportional allocation, so the selection mirrors the corpus rather than
    over-weighting the short documents that a uniform draw would favour. Each
    document is truncated to its first 30 fragments at cut time; the band
    recorded here is the document's TRUE band, which is what the length
    covariate needs, not its post-truncation size.
    """
    by_band = {name: [] for name, _, _ in BANDS}
    for rid, n in counts.items():
        by_band[band_of(n)].append(rid)
    for v in by_band.values():
        v.sort()

    total = len(counts)
    quota = {name: int(round(N_ORDERING_DOCS * len(v) / total))
             for name, v in by_band.items()}

    # Rounding rarely lands on exactly 180; settle the remainder on the largest
    # bands first so no band is pushed past what it actually holds.
    order = sorted(by_band, key=lambda b: -len(by_band[b]))
    while sum(quota.values()) != N_ORDERING_DOCS:
        delta = 1 if sum(quota.values()) < N_ORDERING_DOCS else -1
        for b in order:
            if 0 <= quota[b] + delta <= len(by_band[b]):
                quota[b] += delta
                break

    picked = []
    for name in by_band:
        picked.extend(rng.sample(by_band[name], quota[name]))
    picked.sort()

    return [{
        "record_id": rid,
        "n_fragments_full": counts[rid],
        "n_fragments_capped": min(counts[rid], ORDERING_FRAGMENT_CAP),
        "band": band_of(counts[rid]),
    } for rid in picked], quota


def write_json(path, payload):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)
    return path


def build(key_path, out_dir, seed, force):
    manifest_path = os.path.join(out_dir, "manifest.json")
    if os.path.exists(manifest_path) and not force:
        raise SystemExit(
            f"refusing to overwrite {manifest_path}\n"
            "  The pool partition is built ONCE. Rebuilding it after any cell has\n"
            "  run makes every linkage comparison meaningless, because the same\n"
            "  documents stop co-occurring. Pass --force only if nothing has been\n"
            "  scored against the existing partition yet."
        )

    counts = load_key(key_path)
    rng = random.Random(seed)

    pools, leftover = build_pools(counts, rng)
    linkage = sorted(rng.sample([p["pool_id"] for p in pools], N_LINKAGE_POOLS))
    ordering, quota = select_ordering_docs(counts, rng)

    floors = [p["trivial_floor"]["f1"] for p in pools]
    worst = max(pools, key=lambda p: p["trivial_floor"]["f1"])

    write_json(os.path.join(out_dir, "pools.json"), {
        "pool_size": POOL_SIZE, "n_pools": len(pools), "seed": seed, "pools": pools,
    })
    write_json(os.path.join(out_dir, "linkage_grid.json"), {
        "n_pools": len(linkage), "seed": seed, "pool_ids": linkage,
    })
    write_json(os.path.join(out_dir, "ordering_grid.json"), {
        "n_documents": len(ordering), "fragment_cap": ORDERING_FRAGMENT_CAP,
        "seed": seed, "band_quota": quota, "documents": ordering,
    })
    write_json(manifest_path, {
        "built_at": datetime.now(timezone.utc).isoformat(),
        "seed": seed,
        "source_answer_key": os.path.relpath(key_path, ROOT).replace("\\", "/"),
        "source_sha256": fingerprint(key_path),
        "n_documents": len(counts),
        "n_fragments": sum(counts.values()),
        "pool_size": POOL_SIZE,
        "n_pools": len(pools),
        "documents_pooled": len(pools) * POOL_SIZE,
        "documents_held_out": leftover,
        "n_linkage_pools": N_LINKAGE_POOLS,
        "n_ordering_documents": N_ORDERING_DOCS,
        "ordering_fragment_cap": ORDERING_FRAGMENT_CAP,
        "pool_floor_f1": {
            "min": min(floors), "max": max(floors),
            "mean": sum(floors) / len(floors), "worst_pool": worst["pool_id"],
        },
    })

    print(f"corpus      : {len(counts)} documents, {sum(counts.values())} fragments")
    print(f"pools       : {len(pools)} x {POOL_SIZE} = {len(pools) * POOL_SIZE} documents"
          f"  ({len(leftover)} held out: {', '.join(leftover) or 'none'})")
    print(f"pool floor  : f1 min {min(floors):.4f}  mean {sum(floors)/len(floors):.4f}"
          f"  max {max(floors):.4f}  (worst: {worst['pool_id']})")
    print(f"linkage grid: {len(linkage)} pools")
    print(f"ordering grid: {len(ordering)} documents, capped at {ORDERING_FRAGMENT_CAP} fragments")
    for name, _, _ in BANDS:
        got = sum(1 for d in ordering if d["band"] == name)
        have = sum(1 for n in counts.values() if band_of(n) == name)
        print(f"    band {name:<6} {got:>3} of {have:>3}  ({got / len(ordering):.1%} "
              f"of selection vs {have / len(counts):.1%} of corpus)")
    print(f"\nwrote {out_dir}")


def verify(key_path, out_dir):
    """Check the partition on disk is internally consistent and still current."""
    manifest = json.load(open(os.path.join(out_dir, "manifest.json"), encoding="utf-8"))
    pools = json.load(open(os.path.join(out_dir, "pools.json"), encoding="utf-8"))["pools"]
    linkage = json.load(open(os.path.join(out_dir, "linkage_grid.json"), encoding="utf-8"))
    ordering = json.load(open(os.path.join(out_dir, "ordering_grid.json"), encoding="utf-8"))

    counts = load_key(key_path)
    problems = []

    now = fingerprint(key_path)
    if now != manifest["source_sha256"]:
        problems.append(
            "answer key has CHANGED since the partition was built "
            f"({manifest['source_sha256'][:12]} -> {now[:12]}). "
            "Every linkage number scored against this partition is suspect."
        )

    seen = [m for p in pools for m in p["members"]]
    if len(seen) != len(set(seen)):
        problems.append("a document appears in more than one pool")
    unknown = set(seen) - set(counts)
    if unknown:
        problems.append(f"{len(unknown)} pooled ids are not in the answer key")
    if any(len(p["members"]) != POOL_SIZE for p in pools):
        problems.append("not every pool holds exactly 7 documents")
    for p in pools:
        if [counts[m] for m in p["members"]] != p["fragment_counts"]:
            problems.append(f"{p['pool_id']}: fragment counts do not match the key")
            break

    ids = {p["pool_id"] for p in pools}
    if not set(linkage["pool_ids"]) <= ids:
        problems.append("linkage_grid references pools that do not exist")
    if len(set(linkage["pool_ids"])) != N_LINKAGE_POOLS:
        problems.append(f"linkage_grid is not {N_LINKAGE_POOLS} distinct pools")

    docs = [d["record_id"] for d in ordering["documents"]]
    if len(docs) != len(set(docs)):
        problems.append("ordering_grid repeats a document")
    if len(docs) != N_ORDERING_DOCS:
        problems.append(f"ordering_grid holds {len(docs)}, expected {N_ORDERING_DOCS}")
    for d in ordering["documents"]:
        if d["n_fragments_capped"] != min(counts.get(d["record_id"], -1),
                                          ORDERING_FRAGMENT_CAP):
            problems.append(f"{d['record_id']}: capped count is wrong")
            break

    print(f"pools          : {len(pools)} x {POOL_SIZE}, {len(set(seen))} distinct documents")
    print(f"linkage grid   : {len(linkage['pool_ids'])} pools")
    print(f"ordering grid  : {len(docs)} documents, cap {ordering['fragment_cap']}")
    print(f"key fingerprint: {'MATCHES' if now == manifest['source_sha256'] else 'CHANGED'}")
    if problems:
        print("\nFAILED:")
        for p in problems:
            print(f"  - {p}")
        raise SystemExit(1)
    print("\nPartition is valid and current.")


def parse_args():
    ap = argparse.ArgumentParser(description="Build the fixed pool partition.")
    ap.add_argument("--key", default=DEFAULT_KEY)
    ap.add_argument("--out-dir", default=DEFAULT_OUT)
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--force", action="store_true",
                    help="rebuild even though a partition already exists")
    ap.add_argument("--verify", action="store_true",
                    help="validate the partition on disk instead of building")
    return ap.parse_args()


def main():
    args = parse_args()
    if args.verify:
        verify(args.key, args.out_dir)
    else:
        build(args.key, args.out_dir, args.seed, args.force)


if __name__ == "__main__":
    main()
