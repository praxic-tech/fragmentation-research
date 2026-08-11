#!/usr/bin/env python3
"""
pull_prose.py — Build a post-cutoff clinical-prose corpus from PMC Open Access.

Pipeline:
  1. ESearch PubMed for Case Reports published after Sonnet 5's cutoff (Jan 2026),
     restricted to the PMC Open Access subset.
  2. Convert PMIDs -> PMCIDs (ID Converter).
  3. Confirm each PMCID is in the *commercial-use* OA bucket (OA service) so the
     license is clean (CC0 / CC BY / CC BY-SA / CC BY-ND).
  4. Fetch full text via the BioC API (JSON), keep only the case-narrative body
     (drop abstract, refs, tables, captions).
  5. Split each doc into sentences (sentence granularity — matches current setup).
  6. Emit two JSONL files matching the harness schema:
        prose_fragments.jsonl    {record_id, fragment_id, text}
        prose_answer_key.jsonl   {record_id, order: [fragment_id, ...]}

IMPORTANT — run this where it can reach NCBI (not inside a locked-down sandbox).
NCBI asks for <=3 requests/sec without an API key, <=10/sec with one. Set
NCBI_API_KEY below to go faster and avoid throttling. Always set a real email.

Usage:
    python pull_prose.py --target 500 --out ./data/prose
    python pull_prose.py --target 50 --mindate 2026/02 --out ./data/prose_test
"""

import argparse
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────
EMAIL       = "atejada2@trincoll.edu"      # REQUIRED by NCBI
NCBI_API_KEY = ""                          # optional; raises rate limit to 10/s
TOOL        = "fragmentation-research"

# Sonnet 5 training + reliable-knowledge cutoff is January 2026.
# Filter to Feb 2026+ so nothing in the corpus can have been memorised.
DEFAULT_MINDATE = "2026/02"

EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
IDCONV = "https://pmc.ncbi.nlm.nih.gov/tools/idconv/api/v1/articles/"
OA_SVC = "https://www.ncbi.nlm.nih.gov/pmc/utils/oa/oa.fcgi"
BIOC   = "https://www.ncbi.nlm.nih.gov/research/bionlp/RESTful/pmcoa.cgi/BioC_json/{pmcid}/unicode"

# License strings we accept (commercial-use bucket)
OK_LICENSES = {"CC0", "CC BY", "CC BY-SA", "CC BY-ND"}

# BioC section types to KEEP. BioC tags passages with a "section_type" in infons.
# We want the running clinical narrative, not metadata/refs/tables.
KEEP_SECTIONS = {"CASE", "CASE PRESENTATION", "CASE REPORT", "INTRO",
                 "INTRODUCTION", "DISCUSSION", "METHODS", "RESULTS", "PARAGRAPH"}
DROP_SECTIONS = {"TITLE", "ABSTRACT", "REF", "TABLE", "FIG", "CAPTION", "ACK",
                 "COMP_INT", "AUTH_CONT", "SUPPL", "FOOTNOTE", "KEYWORD"}


# ── HTTP helper with polite rate limiting ────────────────────────────────────
_last = [0.0]
_MIN_INTERVAL = 0.34 if not NCBI_API_KEY else 0.11   # ~3/s or ~10/s

def _get(url, params=None, tries=7):
    if params is None:
        params = {}
    params.setdefault("tool", TOOL)
    params.setdefault("email", EMAIL)
    if NCBI_API_KEY:
        params.setdefault("api_key", NCBI_API_KEY)
    qs = urllib.parse.urlencode(params)
    full = f"{url}?{qs}" if qs else url
    for attempt in range(tries):
        wait = _MIN_INTERVAL - (time.time() - _last[0])
        if wait > 0:
            time.sleep(wait)
        try:
            with urllib.request.urlopen(full, timeout=30) as r:
                _last[0] = time.time()
                return r.read().decode("utf-8", "replace")
        except Exception as e:
            if attempt == tries - 1:
                raise
            # NCBI throws transient 503/429 under sustained load — a long pull will
            # hit one eventually. Exponential backoff (2,4,8,16,32,60s) rides it out;
            # the original fixed 1.5s*n gave up after ~9s and lost the whole run.
            msg = str(e)
            transient = any(s in msg for s in ("503", "429", "500", "502", "504",
                                               "Service Unavailable", "timed out",
                                               "Connection", "reset"))
            back = min(2 ** (attempt + 1), 60) if transient else 1.5 * (attempt + 1)
            print(f"  [retry {attempt+1}/{tries-1}] {msg[:70]} — waiting {back:.0f}s",
                  file=sys.stderr)
            time.sleep(back)
    return ""


# ── Step 1: ESearch for post-cutoff case reports in the OA subset ────────────
def search_pmids(mindate, maxdate, retmax):
    """Return a list of PMIDs for OA-subset case reports in the date window."""
    term = (
        '"case reports"[Publication Type] '
        'AND "pubmed pmc open access"[filter] '     # NB: plain "open access"[filter] is not a
                                                    # valid PubMed filter and silently returns 0
        f'AND ("{mindate}"[Publication Date] : "{maxdate}"[Publication Date])'
    )
    out = _get(f"{EUTILS}/esearch.fcgi", {
        "db": "pubmed", "term": term, "retmax": str(retmax),
        "retmode": "json", "sort": "pub_date",
    })
    try:
        data = json.loads(out)
        return data["esearchresult"]["idlist"]
    except Exception as e:
        print(f"[search] parse error: {e}\n{out[:400]}", file=sys.stderr)
        return []


# ── Step 2: PMID -> PMCID ────────────────────────────────────────────────────
def pmids_to_pmcids(pmids):
    """Batch-convert PMIDs to PMCIDs. Returns dict pmid->pmcid (only those with one)."""
    mapping = {}
    for i in range(0, len(pmids), 200):
        chunk = pmids[i:i+200]
        out = _get(IDCONV, {"ids": ",".join(chunk), "format": "json"})
        try:
            recs = json.loads(out).get("records", [])
            for r in recs:
                if "pmcid" in r and "pmid" in r:
                    mapping[r["pmid"]] = r["pmcid"]   # e.g. "PMC1234567"
        except Exception as e:
            print(f"[idconv] parse error: {e}\n{out[:300]}", file=sys.stderr)
    return mapping


# ── Step 3: license check via OA service ─────────────────────────────────────
def license_ok(pmcid):
    """Query the OA service; accept only commercial-use CC licenses.
    The OA service returns XML with a <record license="..."> attribute."""
    out = _get(OA_SVC, {"id": pmcid})
    m = re.search(r'license="([^"]+)"', out)
    if not m:
        return False
    # Normalise "CC BY-NC-ND" / "CC-BY-NC" -> token list ["CC","BY","NC","ND"].
    # A prefix test is NOT safe here: "CC BY-NC".startswith("CC BY") is True, which
    # would silently admit non-commercial licences into a commercial-use corpus.
    lic = re.sub(r"[-\s]+", " ", m.group(1).strip().upper()).strip()
    if lic.replace(" ", "").startswith("CC0"):
        return True
    parts = lic.split()
    if "NC" in parts:                      # explicitly reject every non-commercial variant
        return False
    return lic in {"CC BY", "CC BY SA", "CC BY ND"}


# ── Step 4: fetch BioC JSON, keep narrative body ─────────────────────────────
# BioC marks headings as passages of type "title_1"/"title_2"/… and body text as
# type "paragraph" (figures/tables/refs carry their own types and are excluded by
# requiring "paragraph"). Case reports are frequently tagged section_type=INTRO
# for the WHOLE article, so section_type alone cannot separate the academic
# framing from the patient narrative — we track the enclosing heading instead.
CASE_HEADING = re.compile(
    r"\bcase\b|presentation|clinical (course|history|findings|presentation)"
    r"|patient (report|history|presentation)", re.I)
STOP_HEADING = re.compile(
    r"discussion|conclusion|introduction|background|literature|review|method"
    r"|acknowledg|reference|declaration|abbreviation|consent|funding|ethic", re.I)


def fetch_body_text(pmcid, case_only=True):
    """Return the case-narrative text for a PMCID, or '' on failure.

    case_only=True  -> only paragraphs under a case-narrative heading
                       ("Case summary", "Case presentation", ...). This matches
                       the register of the existing hand-written corpus.
    case_only=False -> every body paragraph (broader, more academic prose).
    """
    # NB: the BioC endpoint requires the FULL "PMC…" id. Passing the bare numeric
    # part returns "[Error] : No result can be found."
    out = _get(BIOC.format(pmcid=pmcid))
    try:
        doc = json.loads(out)
    except Exception:
        return ""

    paras = []
    collections = doc if isinstance(doc, list) else [doc]
    for coll in collections:
        for d in coll.get("documents", []):
            in_case = False
            for p in d.get("passages", []):
                infons = p.get("infons", {})
                ptype  = (infons.get("type") or "").lower()
                txt    = (p.get("text") or "").strip()
                if not txt:
                    continue

                # Heading passage: update whether we are inside the case narrative
                if ptype.startswith("title"):
                    if STOP_HEADING.search(txt):
                        in_case = False
                    elif CASE_HEADING.search(txt):
                        in_case = True
                    continue

                # Body text only — this drops fig/fig_caption/table/ref/abstract/front
                if ptype != "paragraph":
                    continue
                if case_only and not in_case:
                    continue
                if len(txt.split()) > 5:
                    paras.append(txt)
    return "\n".join(paras)


# ── Step 5: sentence split (granularity = sentence, matching current setup) ──
_SENT = re.compile(r'(?<=[.!?])\s+(?=[A-Z0-9])')

def split_sentences(text):
    text = re.sub(r'\s+', ' ', text).strip()
    sents = [s.strip() for s in _SENT.split(text) if len(s.strip()) > 15]
    return sents


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", type=int, default=500,
                    help="number of usable documents wanted")
    ap.add_argument("--mindate", default=DEFAULT_MINDATE,
                    help="earliest pub date YYYY/MM (default 2026/02, post-cutoff)")
    ap.add_argument("--maxdate", default="2026/12")
    ap.add_argument("--min-frags", type=int, default=4,
                    help="skip docs with fewer than this many sentences")
    ap.add_argument("--max-frags", type=int, default=12,
                    help="truncate docs longer than this many sentences")
    ap.add_argument("--out", default="./data/prose")
    ap.add_argument("--all-sections", action="store_true",
                    help="keep every body paragraph instead of only the case "
                         "narrative (broader, but more academic in register)")
    ap.add_argument("--resume", action="store_true",
                    help="append to an existing corpus and skip already-fetched "
                         "PMCIDs instead of starting over")
    ap.add_argument("--retmax", type=int, default=None,
                    help="candidate PMIDs to fetch (default target*5). Only ~25%% "
                         "survive the licence + narrative filters, so this must "
                         "comfortably exceed --target. PubMed caps it at 10000.")
    args = ap.parse_args()

    if EMAIL.startswith("CHANGE_ME"):
        print("ERROR: set EMAIL at the top of the script (NCBI requires it).",
              file=sys.stderr)
        sys.exit(1)

    outdir = Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)

    # Over-fetch PMIDs since many drop out at licence/body stages (~25% survive).
    retmax = min(args.retmax or args.target * 5, 10000)   # 10000 = PubMed's esearch cap
    print(f"[1/4] searching PubMed (case reports, {args.mindate}–{args.maxdate}) ...")
    pmids = search_pmids(args.mindate, args.maxdate, retmax)
    print(f"      {len(pmids)} PMIDs found")

    print("[2/4] converting PMID -> PMCID ...")
    pmid2pmc = pmids_to_pmcids(pmids)
    pmcids = list(dict.fromkeys(pmid2pmc.values()))
    print(f"      {len(pmcids)} have PMC full text")

    frag_path = outdir / "prose_fragments.jsonl"
    key_path  = outdir / "prose_answer_key.jsonl"

    # Resume: a long pull can die on a transient NCBI error at 97% done. Re-running
    # picks up where it left off instead of discarding everything (the original
    # opened with "w", which clobbered prior work on every restart).
    done_pmcids, kept = set(), 0
    if args.resume and key_path.exists():
        with key_path.open(encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    rec = json.loads(line)
                    done_pmcids.add(rec.get("source_pmcid"))
                    kept += 1
        print(f"      resuming: {kept} documents already on disk")

    mode   = "a" if (args.resume and kept) else "w"
    frag_f = frag_path.open(mode, encoding="utf-8")
    key_f  = key_path.open(mode, encoding="utf-8")

    for idx, pmcid in enumerate(pmcids):
        if kept >= args.target:
            break
        if pmcid in done_pmcids:
            continue
        if not license_ok(pmcid):
            continue
        body = fetch_body_text(pmcid, case_only=not args.all_sections)
        if not body:
            continue
        sents = split_sentences(body)
        if len(sents) < args.min_frags:
            continue
        sents = sents[:args.max_frags]

        rec = f"prose_{kept:04d}"
        order = []
        for j, s in enumerate(sents):
            fid = f"{rec}_frag_{j:03d}"
            order.append(fid)
            frag_f.write(json.dumps({
                "record_id": rec, "fragment_id": fid, "text": s
            }) + "\n")
        key_f.write(json.dumps({"record_id": rec, "order": order,
                                "source_pmcid": pmcid}) + "\n")
        kept += 1
        if kept % 25 == 0:
            print(f"      kept {kept}/{args.target}  (scanned {idx+1} PMCIDs)")

    frag_f.close()
    key_f.close()
    print(f"[4/4] done: {kept} documents -> {outdir}/prose_fragments.jsonl")
    if kept < args.target:
        print(f"      NOTE: only {kept} kept. Widen --maxdate or raise the "
              f"search retmax multiplier to get more.")


if __name__ == "__main__":
    main()
