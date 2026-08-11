#!/usr/bin/env python3
"""
verify_postcutoff.py — GATE 2a.

Confirms every document in a corpus was published AFTER Sonnet 5's January 2026
knowledge cutoff. The prose_v3 pull hit transient 503s and was completed with
--resume, so the date filter is re-verified independently here against NCBI
rather than trusted from the original ESearch query.

Any document dated 2026/01 or earlier is REPORTED, never silently dropped.

Usage:
    python verify_postcutoff.py --data ./data/prose_v3
"""

import argparse
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

EMAIL  = "atejada2@trincoll.edu"
TOOL   = "fragmentation-research"
EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

# Sonnet 5 cutoff. Anything published 2026-02 or later is safe.
CUTOFF_YEAR, CUTOFF_MONTH = 2026, 1     # last UNSAFE month

_last = [0.0]


def _get(url, params, tries=6):
    params.setdefault("tool", TOOL)
    params.setdefault("email", EMAIL)
    full = f"{url}?{urllib.parse.urlencode(params)}"
    for attempt in range(tries):
        wait = 0.34 - (time.time() - _last[0])
        if wait > 0:
            time.sleep(wait)
        try:
            with urllib.request.urlopen(full, timeout=30) as r:
                _last[0] = time.time()
                return r.read().decode("utf-8", "replace")
        except Exception as e:
            if attempt == tries - 1:
                raise
            time.sleep(min(2 ** (attempt + 1), 60))
    return ""


def parse_date(s):
    """'2026 Mar 14' / '2026/03/14' / '2026 Mar' -> (year, month) or None."""
    if not s:
        return None
    m = re.match(r"(\d{4})", s.strip())
    if not m:
        return None
    year = int(m.group(1))
    months = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
              "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12}
    mo = 0
    mm = re.search(r"\b([A-Za-z]{3})", s)
    if mm:
        mo = months.get(mm.group(1).lower(), 0)
    else:
        mm = re.match(r"\d{4}[/-](\d{1,2})", s.strip())
        if mm:
            mo = int(mm.group(1))
    return year, mo


def is_post_cutoff(year, month):
    """Safe iff strictly after 2026-01. Month 0 (year only) is treated as
    UNKNOWN-but-suspect unless the year is clearly later."""
    if year > CUTOFF_YEAR:
        return True
    if year < CUTOFF_YEAR:
        return False
    return month > CUTOFF_MONTH     # month==0 (unknown) -> False, flagged


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="./data/prose_v3")
    args = ap.parse_args()

    key_path = Path(args.data) / "prose_answer_key.jsonl"
    recs = [json.loads(l) for l in key_path.open(encoding="utf-8") if l.strip()]
    pmcids = [r["source_pmcid"] for r in recs]
    by_pmcid = {r["source_pmcid"]: r["record_id"] for r in recs}
    print(f"verifying {len(pmcids)} documents against cutoff "
          f"{CUTOFF_YEAR}-{CUTOFF_MONTH:02d} (safe = published later)\n")

    dates = {}
    for i in range(0, len(pmcids), 200):
        chunk = [p.replace("PMC", "") for p in pmcids[i:i + 200]]
        out = _get(f"{EUTILS}/esummary.fcgi",
                   {"db": "pmc", "id": ",".join(chunk), "retmode": "json"})
        try:
            data = json.loads(out).get("result", {})
        except Exception as e:
            print(f"  [warn] esummary parse failure on batch {i}: {e}", file=sys.stderr)
            continue
        for uid in data.get("uids", []):
            rec = data.get(uid, {})
            # Precedence matters: `pubdate` is often the journal ISSUE date and can
            # be year-only ("2026"), which cannot be tested against a month cutoff.
            # `sortdate`/`epubdate` carry the precise electronic publication date.
            raw = (rec.get("sortdate") or rec.get("epubdate")
                   or rec.get("pubdate") or rec.get("printpubdate") or "")
            dates["PMC" + uid] = raw
        print(f"  fetched dates for {len(dates)}/{len(pmcids)}")

    safe, unsafe, unknown = [], [], []
    for p in pmcids:
        raw = dates.get(p)
        pd = parse_date(raw) if raw else None
        if pd is None:
            unknown.append((p, raw))
            continue
        y, mo = pd
        (safe if is_post_cutoff(y, mo) else unsafe).append((p, raw))

    print(f"\n{'='*64}")
    print(f"  POST-CUTOFF (safe)      : {len(safe)}/{len(pmcids)}")
    print(f"  PRE/AT-CUTOFF (UNSAFE)  : {len(unsafe)}")
    print(f"  UNRESOLVED date         : {len(unknown)}")
    print(f"{'='*64}")

    if unsafe:
        print("\nFLAGGED — published on/before the cutoff, DO NOT include:")
        for p, raw in sorted(unsafe, key=lambda x: x[1] or ""):
            print(f"  {by_pmcid[p]:12s} {p:14s} {raw}")
        Path("flagged_precutoff.txt").write_text(
            "\n".join(f"{by_pmcid[p]}\t{p}\t{raw}" for p, raw in unsafe),
            encoding="utf-8")
        print("\n  -> written to flagged_precutoff.txt")
    if unknown:
        print("\nUNRESOLVED — no parseable date, treat as suspect:")
        for p, raw in unknown[:20]:
            print(f"  {by_pmcid.get(p,'?'):12s} {p:14s} {raw!r}")

    print("\nGATE 2a:", "PASS — every document is post-cutoff"
          if not unsafe and not unknown else "FAIL — see flagged documents above")


if __name__ == "__main__":
    main()
