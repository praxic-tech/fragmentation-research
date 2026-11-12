#!/usr/bin/env python3
"""
pull_disjoint_train.py — training corpus for the trained non-LLM attackers
(RUN_DECISIONS D19: tier 0 position model; later tier 3 cross-encoder).

DISJOINT FROM EVALUATION BY CONSTRUCTION
----------------------------------------
The evaluation corpus (data/prose) is PMC open-access case reports published
2026/02 or later. This corpus is drawn from 2024/01 - 2025/12 publication dates,
and every PMCID that appears anywhere under data/ is excluded as well, so no
evaluation document can be in it. The manifest of kept PMCIDs is written next
to the text so the exclusion is checkable.

Same pipeline as the evaluation corpus, unchanged: the same PubMed query
(case reports, PMC OA filter), the same commercial-use licence check, the same
BioC case-narrative extraction and the same spaCy sentence splitter with the
15-character filter (datagen/pull_prose.py, datagen/pull_prose_v4.py are
imported, not edited). Only the date window and the target differ.

PRIVACY: no personal contact address is sent. pull_prose.py's hard-coded
e-mail is blanked for this process and the tool name is generic.

Order: all PMCIDs across the 24 monthly windows are collected first, then
shuffled with seed 42, so a pull stopped early is still spread over the window.

Usage:
    python datagen/pull_disjoint_train.py --target 20000
    python datagen/pull_disjoint_train.py --target 20000 --resume
Output: data/disjoint_train/documents.jsonl  (one document per line)
        data/disjoint_train/manifest.json    (window, query, exclusions, counts)
"""

import argparse
import glob
import json
import os
import random
import re
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "datagen"))

import pull_prose as PP                     # noqa: E402
PP.EMAIL = ""                               # never send a personal address
PP.TOOL = "pmc-corpus-client"
from pull_prose_v4 import split_sentences   # noqa: E402

import urllib.error                          # noqa: E402

_orig_get = PP._get


def _get_fast_404(url, params=None, tries=7):
    """pull_prose._get retries every error, a 404 included, for ~30 s. A missing
    BioC record is permanent, so here a 404 / 400 returns "" at once (callers
    already treat "" as no record); every other error keeps the original
    backoff. Same rate limit: the first attempt goes through the original."""
    try:
        return _orig_get(url, params, tries=1)
    except urllib.error.HTTPError as e:
        if e.code in (400, 404):
            return ""
    except Exception:
        pass
    return _orig_get(url, params, tries=tries)


_cache = {"url": None, "text": None}


def _get_cached(url, params=None, tries=7):
    """One-entry cache so the licence check and the body fetch share one BioC
    request per document."""
    if params is None and url == _cache["url"]:
        return _cache["text"]
    text = _get_fast_404(url, params, tries)
    if params is None:
        _cache.update(url=url, text=text)
    return text


PP._get = _get_cached


def license_ok_bioc(pmcid):
    """pull_prose.license_ok's decision rule, reading the licence from the BioC
    record's document infons. The OA web service it queried
    (www.ncbi.nlm.nih.gov/pmc/utils/oa/oa.fcgi) now returns 404 for every id,
    including evaluation documents that passed it in 2026-09."""
    out = PP._get(PP.BIOC.format(pmcid=pmcid))
    try:
        doc = json.loads(out)
    except Exception:
        return False
    colls = doc if isinstance(doc, list) else [doc]
    lic = ""
    for coll in colls:
        for d in coll.get("documents", []):
            lic = lic or (d.get("infons", {}) or {}).get("license", "") or ""
    if not lic:
        return False
    lic = re.sub(r"[-\s]+", " ", lic.strip().upper()).strip()
    if lic.replace(" ", "").startswith("CC0"):
        return True
    parts = lic.split()
    if "NC" in parts:
        return False
    return lic in {"CC BY", "CC BY SA", "CC BY ND"}

OUT = os.path.join(ROOT, "data", "disjoint_train")
MONTHS = [f"{y}/{m:02d}" for y in (2024, 2025) for m in range(1, 13)]
MIN_FRAGS = 4


def eval_pmcids():
    """Every PMCID mentioned anywhere under data/ except this corpus."""
    found = set()
    for p in glob.glob(os.path.join(ROOT, "data", "**", "*.json*"), recursive=True):
        if os.path.normpath(p).startswith(os.path.normpath(OUT)):
            continue
        try:
            with open(p, encoding="utf-8", errors="replace") as fh:
                found |= set(re.findall(r"PMC\d{5,}", fh.read()))
        except OSError:
            pass
    return found


def collect_ids(exclude):
    ids = []
    for mo in MONTHS:
        pmids = PP.search_pmids(mo, mo, 10000)
        conv = PP.pmids_to_pmcids(pmids)
        new = [c for c in dict.fromkeys(conv.values()) if c not in exclude]
        print(f"  {mo}: {len(pmids)} PMIDs, {len(new)} PMCIDs kept", flush=True)
        ids.extend((c, mo) for c in new)
    seen, out = set(), []
    for c, mo in ids:
        if c not in seen:
            seen.add(c)
            out.append((c, mo))
    random.Random(42).shuffle(out)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", type=int, default=20000)
    ap.add_argument("--resume", action="store_true")
    a = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)
    doc_p = os.path.join(OUT, "documents.jsonl")
    ids_p = os.path.join(OUT, "candidate_ids.json")
    man_p = os.path.join(OUT, "manifest.json")

    exclude = eval_pmcids()
    print(f"excluding {len(exclude)} PMCIDs found under data/", flush=True)
    if a.resume and os.path.exists(ids_p):
        cands = [tuple(x) for x in json.load(open(ids_p, encoding="utf-8"))]
    else:
        print("collecting candidate PMCIDs, 2024/01 - 2025/12 ...", flush=True)
        cands = collect_ids(exclude)
        json.dump(cands, open(ids_p, "w", encoding="utf-8"))
    assert not ({c for c, _ in cands} & exclude), "evaluation PMCID among candidates"

    done, kept = set(), 0
    if a.resume and os.path.exists(doc_p):
        for line in open(doc_p, encoding="utf-8"):
            if line.strip():
                done.add(json.loads(line)["pmcid"])
        kept = len(done)
    tried_p = os.path.join(OUT, "tried.txt")
    tried = set(open(tried_p, encoding="utf-8").read().split()) if (a.resume and os.path.exists(tried_p)) else set()
    print(f"{len(cands)} candidates; {kept} documents already kept; target {a.target}", flush=True)

    fh = open(doc_p, "a" if a.resume else "w", encoding="utf-8")
    th = open(tried_p, "a" if a.resume else "w", encoding="utf-8")
    t0 = time.time()
    for c, mo in cands:
        if kept >= a.target:
            break
        if c in done or c in tried:
            continue
        th.write(c + "\n")
        th.flush()
        try:
            if not license_ok_bioc(c):
                continue
            body = PP.fetch_body_text(c, case_only=True)
        except Exception as e:          # one bad record never stops the pull
            print(f"  skip {c}: {str(e)[:80]}", flush=True)
            continue
        if not body:
            continue
        sents = split_sentences(body)
        if len(sents) < MIN_FRAGS:
            continue
        fh.write(json.dumps({"pmcid": c, "window": mo, "n_sentences": len(sents),
                             "sentences": sents}) + "\n")
        fh.flush()
        kept += 1
        if kept % 250 == 0:
            el = time.time() - t0
            print(f"  {kept} kept, {el / 60:.1f} min", flush=True)
    fh.close()
    th.close()

    json.dump({"window": [MONTHS[0], MONTHS[-1]],
               "query": "case reports[Publication Type] AND pubmed pmc open access[filter], monthly windows",
               "licence": "commercial-use CC only (pull_prose.license_ok rule, read from BioC document infons; OA service now 404s)",
               "extraction": "pull_prose.fetch_body_text(case_only=True); pull_prose_v4.split_sentences (min 15 chars)",
               "min_sentences": MIN_FRAGS, "shuffle_seed": 42,
               "excluded_pmcids_found_under_data": len(exclude),
               "candidates": len(cands), "documents_kept": kept},
              open(man_p, "w", encoding="utf-8"), indent=2)
    print(f"done: {kept} documents -> {doc_p}", flush=True)


if __name__ == "__main__":
    main()
