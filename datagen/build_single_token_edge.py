"""
build_single_token_edge.py — POST-HOC EXPLORATORY — CONTROLLED SINGLE-TOKEN EDGE-CASE
EXPERIMENT (RUN_DECISIONS D16). Builds the frozen sample, both paired cells, the
(NOT submitted) game-J spec, the provenance record and the price / resource report.
No API calls, no attacker, no reconstruction score.

Hash rule (frozen, as used to generate and price the candidate ordering):
    SHA-256 over UTF-8("single-token-edge-v1" + id), no separator.
Pools      the 46 headline pools ordered by that hash of pool_id; the first 20.
           Existing 7-document membership (data/pools/pools.json, 2026-08-28) kept.
Sentences  the corpus's own segmentation (pull_prose_v4.split_sentences: spaCy,
           per paragraph) on the ORIGINAL source text (data/prose/prose_raw.jsonl)
           with the minimum-length filter DISABLED (min_chars=1: every non-empty
           sentence), so four consecutive sentences are four consecutive source
           sentences. The corpus reference cut is the same function with
           min_chars=15 (reproduced exactly on 500/500 documents).
Excerpt    valid starts 0 .. n-4; start = valid[hash(document_id) mod len(valid)];
           exactly 4 consecutive sentences. No word-count target.
Conditions from the identical excerpt text:
             edge__sentence  4 fragments per document (28 per pool)
             edge__token     one fragment per whitespace-delimited token, verbatim

    python datagen/build_single_token_edge.py
"""

import csv
import glob
import hashlib
import io
import json
import math
import os
import random
import re
import statistics as st
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
for d in ("adversaries", "harness", "analysis", "datagen"):
    sys.path.insert(0, os.path.join(ROOT, d))

import build_excerpt_granularity as BX                         # noqa: E402  (historical usage fits only)
from batch_game import build_spec, headline_docs, load_frame   # noqa: E402
from batch_submit import build_requests, estimate_cost         # noqa: E402
from masking import preflight_stats, reset_preflight_stats     # noqa: E402
from pull_prose_v4 import split_sentences                      # noqa: E402

NS = "single-token-edge-v1"
N_POOLS, N_SENT, N_PERM = 20, 4, 10_000
OUT = "results/single_token_edge"
CELLS = {"sentence": os.path.join(OUT, "edge__sentence"), "token": os.path.join(OUT, "edge__token")}
POOLS_FILE = "data/pools/single_token_edge_pools.json"
SPEC = "runs/single_token_edge_J.json"
CAP, IN_P, OUT_P, TAX = 128_000, 1.0, 5.0, 0.0625
TRIP, WALL = 182.0, 197.64
DEV_SOURCES = {"8-document free-tier probe (O runs, llm-cut defender, Memon)": "results/o_probe",
               "25-document pilot_reference (J pilots, Memon n-sweep, hier smoke)": "results/grid/pilot_reference",
               "llm-cut decision cache (v1/v2/v3 prompt comparisons)": "results/llm_cut_decisions.jsonl",
               "week-6 three-way llm-cut cells": "results/grid/3way_v1"}


def hsh(s):
    return int(hashlib.sha256((NS + s).encode("utf-8")).hexdigest(), 16)


def sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def dev_contact():
    """The documented development contact (RUN_DECISIONS, development history):
    headline documents present in the four recorded development sources."""
    pat, H, out = re.compile(r"prose_\d{4}"), headline_docs(), {}
    for label, path in DEV_SOURCES.items():
        files = [path] if os.path.isfile(path) else glob.glob(os.path.join(path, "**", "*.json*"), recursive=True)
        ids = set()
        for f in files:
            ids |= set(pat.findall(open(f, encoding="utf-8", errors="ignore").read()))
        for d in sorted(ids & H):
            out.setdefault(d, []).append(label)
    return out


def excerpt(sents, rid):
    valid = list(range(0, len(sents) - (N_SENT - 1)))
    assert valid, f"{rid}: fewer than {N_SENT} sentences"
    start = valid[hsh(rid) % len(valid)]
    return start, sents[start:start + N_SENT]


def main():
    raw = {json.loads(l)["record_id"]: json.loads(l)["text"] for l in open("data/prose/prose_raw.jsonl", encoding="utf-8") if l.strip()}
    grid = {p for p, _ in load_frame("data/pools/pools.json", "data/pools/linkage_grid.json")}
    head = [(p, ms) for p, ms in load_frame("data/pools/pools.json") if p not in grid]
    assert len(head) == 46
    pools = sorted(head, key=lambda pm: hsh(pm[0]))[:N_POOLS]
    contact = dev_contact()
    pool_of = {m: p for p, ms in load_frame("data/pools/pools.json") for m in ms}
    assert len(contact) == 21 and len({pool_of[d] for d in contact}) == 18, (len(contact), "matches the D2 record")

    docs, filt_changed = [], 0
    for rank, (pid, members) in enumerate(pools):
        for rid in members:
            sents = split_sentences(raw[rid], 1)                    # NO length filter
            start, ex = excerpt(sents, rid)
            text = " ".join(ex)
            toks = text.split()
            assert " ".join(toks) == " ".join(" ".join(s.split()) for s in ex), rid
            f_start, f_ex = excerpt(split_sentences(raw[rid], 15), rid)     # what the filtered rule would have taken
            filt_changed += f_ex != ex
            docs.append({"rank": rank + 1, "pool": pid, "doc": rid, "n_sentences": len(sents), "start": start,
                         "end": start + N_SENT - 1,
                         "rel_start": start / (len(sents) - N_SENT) if len(sents) > N_SENT else 0.0,
                         "words": len(toks), "short_segments": [s for s in ex if len(s) < 15],
                         "excerpt_sha256": sha(text), "source_sha256": sha(raw[rid]),
                         "dev_contact": contact.get(rid, []), "sentences": ex, "tokens": toks})
    for cond, cdir in CELLS.items():
        os.makedirs(cdir, exist_ok=True)
        with io.open(os.path.join(cdir, "prose_fragments.jsonl"), "w", encoding="utf-8") as ff, \
                io.open(os.path.join(cdir, "prose_answer_key.jsonl"), "w", encoding="utf-8") as fk:
            for d in docs:
                units, tag = (d["sentences"], "es") if cond == "sentence" else (d["tokens"], "et")
                order = []
                for j, t in enumerate(units):
                    fid = f"{d['doc']}_{tag}_{j:03d}"
                    order.append(fid)
                    ff.write(json.dumps({"fragment_id": fid, "record_id": d["doc"], "text": t}) + "\n")
                fk.write(json.dumps({"record_id": d["doc"], "order": order}) + "\n")
        json.dump({"cell": os.path.basename(cdir), "condition": cond,
                   "experiment": "POST-HOC EXPLORATORY — CONTROLLED SINGLE-TOKEN EDGE-CASE EXPERIMENT (D16)",
                   "unit": "one source sentence (unfiltered corpus segmentation)" if cond == "sentence"
                   else "one whitespace-delimited token, verbatim"},
                  open(os.path.join(cdir, "cell_manifest.json"), "w", encoding="utf-8"), indent=2)
    commit = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    json.dump({"what": "POST-HOC EXPLORATORY — CONTROLLED SINGLE-TOKEN EDGE-CASE EXPERIMENT (RUN_DECISIONS D16)",
               "hash_rule": 'SHA-256 of UTF-8("single-token-edge-v1" + id), no separator',
               "pools": [{"rank": i + 1, "pool_id": p, "members": ms} for i, (p, ms) in enumerate(pools)],
               "documents": [{k: v for k, v in d.items() if k not in ("sentences", "tokens")} for d in docs],
               "excerpts_different_from_the_min_chars_15_rule": filt_changed,
               "built_at_commit": commit}, open(POOLS_FILE, "w", encoding="utf-8"), indent=1)

    spec = build_spec([CELLS["sentence"], CELLS["token"]], ["J"], docs=0, pool_size=7, seed=42,
                      tag="single-token-edge-J", pools=[(p, ms) for p, ms in pools], o_docs=[])
    spec["NOT_SUBMITTED"] = ("POST-HOC EXPLORATORY single-token edge-case experiment (D16): submit only on the "
                             "user's explicit launch approval")
    with io.open(SPEC, "w", encoding="utf-8") as fh:
        json.dump(spec, fh, indent=1)
    reset_preflight_stats()
    est = estimate_cost(build_requests(spec))
    pf = preflight_stats()
    json.dump({"spec": SPEC, "spec_sha256": hashlib.sha256(open(SPEC, "rb").read()).hexdigest(),
               "git_commit_at_build": commit, "pools": POOLS_FILE, "cells": list(CELLS.values()),
               "n_requests": len(spec["requests"]), "estimate": est,
               "preflight": {"checked": pf["checked"], "blocked": pf["blocked"]}},
              open(SPEC.replace(".json", "_manifest.json"), "w", encoding="utf-8"), indent=2)

    # ── resource and price estimates from our own completed one-shot J answers ─
    E = BX.empirical()
    rng = random.Random(42)
    per = []
    for s in spec["sidecar"].values():
        cond = "sentence" if s["cell"] == "edge__sentence" else "token"
        n = s["n_fragments"]
        mu = E["a"] + E["b"] * math.log(n)
        draws = [min(CAP, math.exp(mu + rng.choice(E["resid"]))) for _ in range(20000)]
        per.append({"pool": s["unit"], "cond": cond, "n": n, "in_tok": E["a_in"] + E["b_in"] * len(s["prompt"]),
                    "out_med": min(CAP, math.exp(mu)), "out_mean": st.fmean(draws), "draws": draws,
                    "p_rbnc": sum(math.exp(mu + r) >= CAP for r in E["resid"]) / len(E["resid"])})
    R = list(csv.DictReader(open("results/final_analysis/MASTER_RESULTS.csv", encoding="utf-8")))
    J = [r for r in R if r["game"] == "J" and r["attacker"] == "One-shot Sonnet"]
    big = [r for r in J if float(r["n_fragments"]) >= 400]
    spent = json.load(open("results/run_ledger.json"))["spend"]["observed_usd"]

    def cst(sel):
        return sum(p["in_tok"] / 1e6 * IN_P + p["out_mean"] / 1e6 * OUT_P for p in sel)
    S, T = [p for p in per if p["cond"] == "sentence"], [p for p in per if p["cond"] == "token"]
    exp = 1.12 * (cst(S) + cst(T))
    tot = sorted(sum(p["in_tok"] / 1e6 * IN_P + p["draws"][k] / 1e6 * OUT_P for p in per) for k in range(20000))
    worst = sum(p["in_tok"] / 1e6 * IN_P + CAP / 1e6 * OUT_P for p in per)
    words = [d["words"] for d in docs]
    tk = [p["n"] for p in T]
    L = ["# POST-HOC EXPLORATORY — CONTROLLED SINGLE-TOKEN EDGE-CASE EXPERIMENT: frozen design, provenance, price",
         "", "RUN_DECISIONS D16. **Frozen; NOT submitted.** Spec `runs/single_token_edge_J.json` (40 requests: 20 "
         "pools × 2 conditions), marked NOT_SUBMITTED. Design document: `docs/single_token_edge_design.md`.", "",
         "## Pools (hash order) and development contact", "",
         "| rank | pool | documents | token frags | documents with documented prior scored development contact |",
         "|---|---|---|---|---|"]
    for i, (p, ms) in enumerate(pools):
        dc = [d for d in docs if d["pool"] == p and d["dev_contact"]]
        L.append(f"| {i + 1} | {p} | {', '.join(m[6:] for m in ms)} | {next(x['n'] for x in T if x['pool'] == p)} | "
                 f"{'; '.join(d['doc'] + ' (' + ', '.join(s.split(' (')[0] for s in d['dev_contact']) + ')' for d in dc) or '—'} |")
    ndc = sum(bool(d["dev_contact"]) for d in docs)
    L += ["", f"{ndc} of the 140 selected documents, in {len({d['pool'] for d in docs if d['dev_contact']})} of the 20 "
          "pools, are among the 21 headline documents with documented prior scored development contact (RUN_DECISIONS, "
          "development history). Provenance only: nothing is excluded, replaced, reordered or resampled.", "",
          "## Documents and excerpts", "",
          "| pool | document | sentences (unfiltered) | excerpt | relative start | words | short (<15 char) segments | excerpt sha256 | source sha256 |",
          "|---|---|---|---|---|---|---|---|---|"]
    for d in docs:
        L.append(f"| {d['pool']} | {d['doc']} | {d['n_sentences']} | {d['start']}–{d['end']} | {d['rel_start']:.2f} | "
                 f"{d['words']} | {len(d['short_segments'])} | {d['excerpt_sha256'][:12]} | {d['source_sha256'][:12]} |")
    L += ["", f"Excerpts that differ from what the ≥15-character-filtered sequence would have given: {filt_changed} of 140. "
          f"Excerpts containing a genuine sub-15-character source segment (e.g. a figure-citation stub): "
          f"{sum(bool(d['short_segments']) for d in docs)}.", "",
          "## Resources and price (API credit at the batch rate; the ledger's rate)", "",
          "| | value |", "|---|---|",
          f"| excerpt words per document | median {st.median(words)}, range {min(words)}–{max(words)} |",
          "| sentence fragments per pool | 28 |",
          f"| token fragments per pool | median {st.median(tk)}, range {min(tk)}–{max(tk)} |",
          f"| input tokens per request (sentence / token) | {min(p['in_tok'] for p in S):.0f}–{max(p['in_tok'] for p in S):.0f} / "
          f"{min(p['in_tok'] for p in T):.0f}–{max(p['in_tok'] for p in T):.0f} |",
          f"| output tokens, fit median (sentence / token) | ~{st.median(p['out_med'] for p in S):.0f} / "
          f"{min(p['out_med'] for p in T):.0f}–{max(p['out_med'] for p in T):.0f} (capped at 128k) |",
          f"| P(128k) per token pool | {min(p['p_rbnc'] for p in T):.0%}–{max(p['p_rbnc'] for p in T):.0%}; expected "
          f"{sum(p['p_rbnc'] for p in T):.1f} of 20 token requests |",
          f"| sentence arm | ${cst(S):.2f} |", f"| token arm | ${cst(T):.2f} |",
          f"| **expected total incl. ~12% repairs** | **${exp:.2f}** (P95 ${1.12 * tot[19000]:.2f}); cash with tax ${exp * (1 + TAX):.2f} |",
          f"| absolute worst case (all 40 requests at 128k) | ${worst:.2f}; cash ${worst * (1 + TAX):.2f} |",
          f"| ledger now → after expected / after worst | ${spent:.2f} → ${spent + exp:.2f} / ${spent + worst:.2f} |",
          f"| headroom after expected (tripwire / wall) | ${TRIP - spent - exp:.2f} / ${WALL - spent - exp:.2f} |",
          f"| headroom after worst (tripwire / wall) | ${TRIP - spent - worst:.2f} / ${WALL - spent - worst:.2f} |",
          "", "**Extrapolation:** the output model is a log-log fit to the answering call's output tokens over "
          f"{E['n_units']} completed one-shot J answers, all with sentence-sized or larger fragments; historical units "
          f"with ≥ 400 fragments: {len(big)}, RBNC {sum(r['completion'] == 'rbnc' for r in big)}, answering-call output "
          f"{sorted(int(float(r['answer_call_output_tokens'])) for r in big)}. Token pools here exceed the historical "
          "maximum (537); the RBNC risk and output are extrapolated and uncertain in both directions."]
    open(os.path.join(OUT, "DESIGN_REPORT.md"), "w", encoding="utf-8").write("\n".join(L) + "\n")
    json.dump({"what": "frozen design parameters (D16)", "hash_rule": 'SHA-256 of UTF-8("single-token-edge-v1" + id), no separator',
               "n_pools": N_POOLS, "n_documents": 7 * N_POOLS, "sentences_per_excerpt": N_SENT,
               "segmentation": "pull_prose_v4.split_sentences(prose_raw, min_chars=1)",
               "conditions": ["sentence", "token"], "permutations_per_pool_condition_null": N_PERM,
               "null_seed": 'numpy PCG64 seeded by SHA-256("single-token-edge-v1|" + pool + "|" + condition + "|" + kind)[:16]',
               "null_kinds": {"oracle-size": "PRIMARY", "predicted-structure": "ROBUSTNESS"},
               "primary_outcome": "paired A_VJ(sentence) - A_VJ(token), oracle-size null",
               "bootstrap": {"resamples": 10000, "seed": 42, "level": 0.95, "unit": "pool, paired"},
               "sign_test": "exact two-sided; zero differences are ties, omitted from the denominator",
               "spec": SPEC, "pools_file": POOLS_FILE, "cells": list(CELLS.values())},
              open(os.path.join(OUT, "FROZEN_DESIGN.json"), "w", encoding="utf-8"), indent=2)
    print("\n".join(L[:30]))
    print("...\n" + "\n".join(L[-20:]))
    print(f"\nspec {SPEC}: {len(spec['requests'])} requests, preflight {pf['checked']} checked / {pf['blocked']} blocked")


if __name__ == "__main__":
    main()
