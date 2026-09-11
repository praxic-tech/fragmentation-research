#!/usr/bin/env python3
"""
llm_cut_prompt_compare.py — compare llm-cut prompts on one fixed document sample.

NO API CALLS. Reads the decision cache (results/llm_cut_decisions.jsonl) and the
cells written by `llm_cutter.py --out-dir results/llm_cut_prompt_compare/<prompt>`.

Per prompt: fragments/doc, % cuts mid-clause (via cut_position_profile), per-doc
cut rate (cuts / available boundaries) mean and sample stdev, docs cut at every
available boundary, input/output tokens, and failures (sample docs with no
cached decision).

Usage:
    python analysis/llm_cut_prompt_compare.py
    python analysis/llm_cut_prompt_compare.py --model moonshotai/kimi-k3
"""

import argparse
import json
import statistics as st
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "analysis"))

from cut_position_profile import load_jsonl, profile_cell, _pct  # noqa: E402

PROMPTS = ["v1", "v2-adversarial", "v3-strategist"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="moonshotai/kimi-k3")
    ap.add_argument("--units", default="clause")
    ap.add_argument("--sample", default=str(ROOT / "data" / "pools" / "llm_cutter_prompt_sample.json"))
    ap.add_argument("--cache", default=str(ROOT / "results" / "llm_cut_decisions.jsonl"))
    ap.add_argument("--cells", default=str(ROOT / "results" / "llm_cut_prompt_compare"))
    ap.add_argument("--raw", default=str(ROOT / "data" / "prose" / "prose_raw.jsonl"))
    ap.add_argument("--json", help="also write the table here")
    args = ap.parse_args()

    sample = [d["record_id"] for d in json.load(open(args.sample))["documents"]]
    rows = {}
    for r in load_jsonl(args.cache):
        if r.get("model") == args.model and r.get("units", "clause") == args.units:
            rows[(r["record_id"], r.get("prompt", "v1"))] = r   # last row wins
    raw_by_id = {r["record_id"]: r["text"] for r in load_jsonl(args.raw)}

    out = {}
    print(f"model={args.model} units={args.units} sample={len(sample)} docs")
    print(f"{'prompt':<16}{'done':>6}{'frags/doc':>11}{'mid-cl%':>9}{'rate':>7}"
          f"{'stdev':>7}{'all-cut':>9}{'in tok':>9}{'out tok':>9}")
    for p in PROMPTS:
        got = [rows[(rid, p)] for rid in sample if (rid, p) in rows]
        if not got:
            print(f"{p:<16}{0:>6}   (no decisions)")
            continue
        frags = [len(r["cut_points"]) + 1 for r in got]
        rates = [len(r["cut_points"]) / (r["n_units"] - 1) for r in got if r["n_units"] > 1]
        all_cut = [r["record_id"] for r in got if len(r["cut_points"]) == r["n_units"] - 1]
        cell = Path(args.cells) / p
        mid = None
        if (cell / "prose_fragments.jsonl").exists():
            mid = _pct(profile_cell(cell, raw_by_id)["btype"], "mid-clause")
        in_tok = sum(r.get("in_tokens") or 0 for r in got)
        out_tok = sum(r.get("out_tokens") or 0 for r in got)
        res = {
            "docs_done": len(got),
            "failures": len(sample) - len(got),
            "frags_per_doc": st.mean(frags),
            "mid_clause_pct": mid,
            "cut_rate_mean": st.mean(rates),
            "cut_rate_stdev": st.stdev(rates) if len(rates) > 1 else 0.0,
            "docs_cut_every_boundary": len(all_cut),
            "docs_cut_every_boundary_ids": all_cut,
            "in_tokens": in_tok,
            "out_tokens": out_tok,
            "per_doc": {r["record_id"]: f"{len(r['cut_points'])}/{r['n_units'] - 1}" for r in got},
        }
        out[p] = res
        mid_s = f"{mid:.1f}" if mid is not None else "n/a"
        print(f"{p:<16}{len(got):>6}{res['frags_per_doc']:>11.1f}{mid_s:>9}"
              f"{res['cut_rate_mean']:>7.2f}{res['cut_rate_stdev']:>7.3f}"
              f"{len(all_cut):>9}{in_tok:>9,}{out_tok:>9,}")
    print()
    for p, res in out.items():
        print(f"{p}: " + "  ".join(f"{k}={v}" for k, v in res["per_doc"].items()))
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(out, f, indent=2)


if __name__ == "__main__":
    main()
