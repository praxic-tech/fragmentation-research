"""
build_final_O_specs.py — the frozen headline O and grid O specs (steps 4-5,
released by the user 2026-09-13, RUN_DECISIONS D12). No API calls.

The documents are EXACTLY the samples that priced the approved plan, taken from
analysis/budget_final.py itself rather than re-implemented:
  headline O  100 of the 322 headline documents: proportional to the length
              bands, largest remainder, seeded within bands ('headline-O-100').
              Full-length semantic x sentence cut (data/prose), as headline J.
  grid O      the first 30 of the seeded order of the 168 pool 2-25 documents
              ('grid-O-60'), the same 30 in all 9 retained cells. Three waves of
              10 documents x 9 cells, so each wave's worst case (every request
              at 128k) fits under the ledger's hard limit, and a wave that stops
              leaves every cell equally covered.
Selection reads document ids and fragment counts only: no text, score or outcome.

    python runs/build_final_O_specs.py
"""

import contextlib
import hashlib
import io
import json
import os
import subprocess
import sys
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
for d in ("adversaries", "harness", "analysis"):
    sys.path.insert(0, os.path.join(ROOT, d))

sys.argv = sys.argv[:1]                         # budget_final parses its own flags at import
with contextlib.redirect_stdout(io.StringIO()):
    import budget_final as BF                   # noqa: E402  the sample rules that priced the plan

from batch_game import build_spec, headline_docs, load_frame    # noqa: E402
from batch_submit import build_requests, estimate_cost           # noqa: E402
from masking import preflight_stats, reset_preflight_stats       # noqa: E402
from run_ledger import HARD_LIMIT, Ledger                        # noqa: E402

HEAD_SPEC = "runs/final_headlineO.json"
GRID_SPECS = [f"runs/final_gridO_w{k}.json" for k in (1, 2, 3)]
PER_WAVE = 10
RULE_HEAD = ("100 of the 322 headline documents, proportional to the length bands "
             f"{BF.BANDS} (fragments per document), largest remainder, ordered within a band by "
             "sha256('headline-O-100|' + record_id); analysis/budget_final.py head_o_sample. "
             "Full-length semantic x sentence cut (data/prose).")
RULE_GRID = ("The 168 documents of grid pools 2-25 ordered by sha256('grid-O-60|' + record_id); "
             "the first 30 (analysis/budget_final.py o_order), the same documents in all 9 retained cells.")


def sha_file(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def write(spec, path, rule, commit):
    spec["NOT_SUBMITTED"] = "steps 4-5 (headline O, grid O): submit only on the user's explicit go"
    with io.open(path, "w", encoding="utf-8") as fh:
        json.dump(spec, fh, indent=1)
    reset_preflight_stats()
    est = estimate_cost(build_requests(spec))
    pf = preflight_stats()
    man = {"spec": path, "spec_sha256": sha_file(path), "git_commit": commit, "rule": rule,
           "o_docs": spec["build"]["o_docs"], "cells": spec["build"]["cells"],
           "n_requests": len(spec["requests"]), "expected_usd": spec["expected_usd"],
           "max_tokens": sorted({r["max_tokens"] for r in spec["requests"]}),
           "estimate": est, "preflight": {"checked": pf["checked"], "blocked": pf["blocked"]}}
    with io.open(path.replace(".json", "_manifest.json"), "w", encoding="utf-8") as fh:
        json.dump(man, fh, indent=2)
    return man


def main():
    commit = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    head_all = headline_docs()
    frame = load_frame("data/pools/pools.json", "data/pools/linkage_grid.json")
    pool1 = set(frame[0][1])
    dev = {m for _p, ms in frame[1:] for m in ms}
    head = BF.head_o_sample(BF.HEAD_O_DOCS)
    grid30 = BF.o_order[:BF.GRID_O_DOCS]
    assert len(head) == len(set(head)) == 100 and set(head) <= head_all, "headline O sample"
    assert len(grid30) == len(set(grid30)) == 30 and set(grid30) <= dev, "grid O sample"
    assert not set(grid30) & head_all and not set(grid30) & pool1, "grid O touches headline or pool 1"
    cells = [os.path.join("results", "grid_A", c) for c in BF.KEEP]

    h = build_spec(["data/prose"], ["O"], docs=0, pool_size=7, seed=42, tag="final-headlineO",
                   pools=[], o_docs=head)
    mans = [write(h, HEAD_SPEC, RULE_HEAD, commit)]
    for k, path in enumerate(GRID_SPECS):
        wave = grid30[k * PER_WAVE:(k + 1) * PER_WAVE]
        g = build_spec(cells, ["O"], docs=0, pool_size=7, seed=42, tag=f"final-gridO-w{k + 1}",
                       pools=[], o_docs=wave, forbid_docs=head_all)
        mans.append(write(g, path, RULE_GRID + f" Wave {k + 1}: documents {k * PER_WAVE + 1}-"
                                               f"{(k + 1) * PER_WAVE} of that order.", commit))
    for m, spec_path in zip(mans, [HEAD_SPEC] + GRID_SPECS):
        spec = json.load(open(spec_path, encoding="utf-8"))
        assert all(r["game"] == "O" for r in spec["requests"]), spec_path
        assert m["max_tokens"] == [128000], spec_path
        assert m["preflight"]["blocked"] == 0, spec_path

    bands = Counter(next(f"{lo}-{hi if hi < 10 ** 9 else '+'}" for lo, hi in BF.BANDS if lo <= BF.nfr[d] <= hi)
                    for d in head)
    frs = sorted(BF.nfr[d] for d in head)
    print(f"headline O: 100 documents; per length band {dict(bands)}; fragments per document "
          f"min {frs[0]}, median {frs[50]}, max {frs[-1]}")
    print(f"grid O: 30 documents x {len(cells)} cells, in 3 waves of {PER_WAVE} documents")
    led = Ledger()
    exp = worst = 0.0
    for m in mans:
        w = m["estimate"]["est_cost_worst_case"]
        exp += m["expected_usd"]
        worst += w
        print(f"  {m['spec']:<30} {m['n_requests']:>4} requests  expected ${m['expected_usd']:6.2f}  "
              f"worst ${w:6.2f}  (ledger ${led.committed:.2f} + worst = ${led.committed + w:.2f} vs hard "
              f"limit ${HARD_LIMIT:.2f})  preflight {m['preflight']['checked']} checked / "
              f"{m['preflight']['blocked']} blocked")
    print(f"  total expected ${exp:.2f} (the specs' own forecast; one repair round is extra)")


if __name__ == "__main__":
    main()
