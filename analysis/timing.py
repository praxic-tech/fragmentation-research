#!/usr/bin/env python3
"""
timing.py — per-document wall-clock instrumentation for adversary runs.

Set up now so the compute-vs-length curve comes for free the first time any
adversary runs on prose_v4. Records seconds alongside the document's fragment
count, so cost can be plotted against length with no extra API spend and no
re-run.

Usage:

    from timing import DocTimer

    with DocTimer("results/timing_memon_v4.jsonl", method="memon-fixed",
                  corpus="prose_v4") as t:
        for rec_id, frag_ids in documents.items():
            with t.doc(rec_id, len(frag_ids)):
                guess = order_fn(frag_ids)          # timed region

    # afterwards
    python timing.py results/timing_memon_v4.jsonl      # prints the curve

Each row: {record_id, n_fragments, seconds, method, corpus}
"""

import json
import sys
import time
from contextlib import contextmanager
from pathlib import Path


class DocTimer:
    def __init__(self, out_path, method="", corpus=""):
        self.path = Path(out_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.method = method
        self.corpus = corpus
        self._fh = None
        self.rows = []

    def __enter__(self):
        self._fh = self.path.open("w", encoding="utf-8")
        return self

    def __exit__(self, *exc):
        if self._fh:
            self._fh.close()
        return False

    @contextmanager
    def doc(self, record_id, n_fragments):
        t0 = time.perf_counter()
        try:
            yield
        finally:
            dt = time.perf_counter() - t0
            row = {"record_id": record_id, "n_fragments": int(n_fragments),
                   "seconds": round(dt, 6), "method": self.method,
                   "corpus": self.corpus}
            self.rows.append(row)
            if self._fh:
                self._fh.write(json.dumps(row) + "\n")
                self._fh.flush()


def report(path):
    """Print the compute-vs-length curve from a timing log."""
    rows = [json.loads(l) for l in Path(path).open(encoding="utf-8") if l.strip()]
    if not rows:
        print("no rows")
        return
    import statistics as st
    tot = sum(r["seconds"] for r in rows)
    print(f"{len(rows)} documents | total {tot:.2f}s | "
          f"mean {tot/len(rows):.4f}s/doc")
    buckets = {}
    for r in rows:
        n = r["n_fragments"]
        lo = (n // 10) * 10
        buckets.setdefault((lo, lo + 9), []).append(r["seconds"])
        # per-fragment cost scaling
    print(f"\n{'n_fragments':>14s} {'docs':>6s} {'mean s':>10s} {'s/frag':>10s}")
    for (lo, hi), vals in sorted(buckets.items()):
        mid = (lo + hi) / 2 or 1
        print(f"{f'{lo}-{hi}':>14s} {len(vals):6d} {st.mean(vals):10.4f} "
              f"{st.mean(vals)/mid:10.6f}")
    ns = [r["n_fragments"] for r in rows]
    ss = [r["seconds"] for r in rows]
    if len(set(ns)) > 1:
        mn, ms = st.mean(ns), st.mean(ss)
        cov = sum((n - mn) * (s - ms) for n, s in zip(ns, ss))
        vn = sum((n - mn) ** 2 for n in ns)
        if vn:
            print(f"\nlinear fit: seconds ~ {cov/vn:.6f} * n_fragments + "
                  f"{ms - (cov/vn)*mn:.4f}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("usage: python timing.py <timing_log.jsonl>")
    report(sys.argv[1])
