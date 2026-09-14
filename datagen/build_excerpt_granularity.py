"""
build_excerpt_granularity.py — POST-HOC EXPLORATORY — CONTROLLED EXCERPT GRANULARITY
EXPERIMENT (RUN_DECISIONS D15). DESIGN ONLY: builds the frozen selection, the two
paired cells, the pools and the (NOT submitted) game-J spec, and writes the
price / resource report. No API calls, no attacker scores read.

Selection   the 500 corpus documents ordered by sha256('xgran-select-v1|' + record_id);
            the first 70, dealt in that order into 10 pools of 7. Independent of any
            attacker score, difficulty, topic or length (every document already meets
            the only requirement: a whole-sentence run of >= 40 words exists).
Excerpt     sentences = the corpus's reference sentence cut (data/prose). Valid starts
            are the sentences from which the rest of the document still reaches 40
            words; the start is valid[ sha256('xgran-start-v1|' + record_id) mod len ].
            Whole sentences are taken until the running word count reaches 40; the
            sentence that crosses 40 is kept whole. No sentence is cut.
Conditions  from the SAME excerpt text:
              excerpt__sentence  one fragment per sentence
              excerpt__token     one fragment per whitespace-delimited token,
                                 verbatim (case and punctuation untouched)

    python datagen/build_excerpt_granularity.py
"""

import csv
import datetime
import hashlib
import io
import json
import math
import os
import random
import statistics as st
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
for d in ("adversaries", "harness", "analysis"):
    sys.path.insert(0, os.path.join(ROOT, d))

import numpy as np                                               # noqa: E402

SEL_SALT, START_SALT = "xgran-select-v1", "xgran-start-v1"
TARGET_WORDS, N_POOLS, POOL = 40, 10, 7
OUT = "results/excerpt_granularity"
CELLS = {"sentence": os.path.join(OUT, "excerpt__sentence"), "token": os.path.join(OUT, "excerpt__token")}
POOLS_FILE = "data/pools/excerpt_granularity_pools.json"
SPEC = "runs/xgran_J.json"
CAP = 128_000
IN_PRICE, OUT_PRICE = 1.0, 5.0                                  # batch $/M, as the ledger settles


def h(salt, rid):
    return int(hashlib.sha256(f"{salt}|{rid}".encode("utf-8")).hexdigest(), 16)


def load(p):
    return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]


def sha_file(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def build_excerpts():
    key = {r["record_id"]: r["order"] for r in load("data/prose/prose_answer_key.jsonl")}
    text = {r["fragment_id"]: r["text"] for r in load("data/prose/prose_fragments.jsonl")}
    ranked = sorted(key, key=lambda r: h(SEL_SALT, r))
    chosen = ranked[:N_POOLS * POOL]
    pools = [(f"xpool_{i:02d}", chosen[i * POOL:(i + 1) * POOL]) for i in range(N_POOLS)]
    ex = {}
    for rid in chosen:
        sents = [text[f] for f in key[rid]]
        w = [len(s.split()) for s in sents]
        valid = [s for s in range(len(sents)) if sum(w[s:]) >= TARGET_WORDS]
        assert valid, f"{rid}: no whole-sentence run reaches {TARGET_WORDS} words"
        start = valid[h(START_SALT, rid) % len(valid)]
        end, total = start, 0
        while total < TARGET_WORDS:
            total += w[end]
            end += 1
        chunk = sents[start:end]
        tokens = " ".join(chunk).split()
        # both cuts reproduce the identical excerpt text (whitespace-normalised)
        assert " ".join(tokens) == " ".join(" ".join(s.split()) for s in chunk), rid
        ex[rid] = {"start_sentence": start, "end_sentence": end - 1, "n_doc_sentences": len(sents),
                   "sentences": chunk, "tokens": tokens, "words": len(tokens), "n_sentences": len(chunk)}
    return pools, ex


def write_cells(pools, ex):
    for cond, cdir in CELLS.items():
        os.makedirs(cdir, exist_ok=True)
        with io.open(os.path.join(cdir, "prose_fragments.jsonl"), "w", encoding="utf-8") as ff, \
                io.open(os.path.join(cdir, "prose_answer_key.jsonl"), "w", encoding="utf-8") as fk:
            for _pid, members in pools:
                for rid in members:
                    units = ex[rid]["sentences"] if cond == "sentence" else ex[rid]["tokens"]
                    tag = "xs" if cond == "sentence" else "xt"
                    order = []
                    for j, t in enumerate(units):
                        fid = f"{rid}_{tag}_{j:03d}"
                        order.append(fid)
                        ff.write(json.dumps({"fragment_id": fid, "record_id": rid, "text": t}) + "\n")
                    fk.write(json.dumps({"record_id": rid, "order": order}) + "\n")
        json.dump({"cell": os.path.basename(cdir), "experiment": "POST-HOC EXPLORATORY — CONTROLLED EXCERPT "
                   "GRANULARITY EXPERIMENT (D15)", "condition": cond,
                   "unit": "one sentence of the reference cut" if cond == "sentence" else
                   "one whitespace-delimited token, verbatim",
                   "source": "data/prose (reference sentence cut)", "target_words": TARGET_WORDS,
                   "selection_salt": SEL_SALT, "start_salt": START_SALT},
                  open(os.path.join(cdir, "cell_manifest.json"), "w", encoding="utf-8"), indent=2)


def empirical():
    """Our completed one-shot J answers: input tokens vs prompt size, and the
    answering call's output tokens vs fragment count (log-log)."""
    R = list(csv.DictReader(open("results/final_analysis/MASTER_RESULTS.csv", encoding="utf-8")))
    J = [r for r in R if r["game"] == "J" and r["attacker"] == "One-shot Sonnet"]
    done = [r for r in J if r["completion"] == "completed" and r["answer_call_output_tokens"]]
    pc = np.array([float(r["prompt_chars"]) for r in done])
    it = np.array([float(r["input_tokens"]) for r in done])
    # the answering call's input only (a repair adds a second prompt): per-unit input / calls is not
    # stored, so fit on units without a repair
    clean = [i for i, r in enumerate(done) if r["repaired"] != "True"]
    b_in, a_in = np.polyfit(pc[clean], it[clean], 1)
    n = np.array([float(r["n_fragments"]) for r in done])
    out = np.array([float(r["answer_call_output_tokens"]) for r in done])
    b, a = np.polyfit(np.log(n), np.log(out), 1)
    resid = np.log(out) - (a + b * np.log(n))
    near = [r for r in J if 230 <= float(r["n_fragments"]) <= 330]
    near_done = [r for r in near if r["completion"] == "completed"]
    return {"a_in": a_in, "b_in": b_in, "a": a, "b": b, "resid": resid, "n_units": len(done),
            "n_clean": len(clean),
            "near": {"units": len(near), "rbnc": sum(r["completion"] == "rbnc" for r in near),
                     "answer_ge_100k": sum(float(r["answer_call_output_tokens"]) >= 100_000 for r in near_done),
                     "answer_median": st.median(float(r["answer_call_output_tokens"]) for r in near_done)},
            "small": {"units": sum(float(r["n_fragments"]) <= 40 for r in done),
                      "answer_median": st.median(float(r["answer_call_output_tokens"]) for r in done
                                                 if float(r["n_fragments"]) <= 40)}}


def main():
    pools, ex = build_excerpts()
    write_cells(pools, ex)
    commit = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    json.dump({"what": "POST-HOC EXPLORATORY — CONTROLLED EXCERPT GRANULARITY EXPERIMENT (RUN_DECISIONS D15)",
               "rule": f"500 documents ordered by sha256('{SEL_SALT}|' + record_id); first 70; pools of 7 in that "
                       f"order. Excerpt start: sha256('{START_SALT}|' + record_id) mod valid starts; whole "
                       f"sentences to >= {TARGET_WORDS} words. No score, difficulty, topic or length criterion.",
               "pools": [{"pool_id": p, "members": m} for p, m in pools],
               "excerpts": {rid: {k: v for k, v in e.items() if k not in ("sentences", "tokens")}
                            for rid, e in ex.items()},
               "built_at_commit": commit}, open(POOLS_FILE, "w", encoding="utf-8"), indent=1)

    from batch_game import build_spec, headline_docs, load_frame
    from batch_submit import build_requests, estimate_cost
    from masking import preflight_stats, reset_preflight_stats
    spec = build_spec([CELLS["sentence"], CELLS["token"]], ["J"], docs=0, pool_size=POOL, seed=42,
                      tag="xgran-J", pools=pools, o_docs=[])
    spec["NOT_SUBMITTED"] = ("POST-HOC EXPLORATORY excerpt granularity experiment (D15): submit only on the "
                             "user's explicit approval of the price / resource report")
    with io.open(SPEC, "w", encoding="utf-8") as fh:
        json.dump(spec, fh, indent=1)
    reset_preflight_stats()
    est = estimate_cost(build_requests(spec))
    pf = preflight_stats()
    json.dump({"spec": SPEC, "spec_sha256": sha_file(SPEC), "git_commit": commit, "pools": POOLS_FILE,
               "cells": list(CELLS.values()), "n_requests": len(spec["requests"]), "estimate": est,
               "preflight": {"checked": pf["checked"], "blocked": pf["blocked"]}},
              open(SPEC.replace(".json", "_manifest.json"), "w", encoding="utf-8"), indent=2)

    # ── estimates from our own completed one-shot J answers ─────────────────
    E = empirical()
    rng = random.Random(42)
    head = headline_docs()
    grid = {m for _p, ms in load_frame("data/pools/pools.json", "data/pools/linkage_grid.json") for m in ms}
    rows, per_req = [], []
    for s in spec["sidecar"].values():
        cond = "sentence" if s["cell"] == "excerpt__sentence" else "token"
        nfr = s["n_fragments"]
        in_tok = E["a_in"] + E["b_in"] * len(s["prompt"])
        mu = E["a"] + E["b"] * math.log(nfr)
        draws = [min(CAP, math.exp(mu + rng.choice(E["resid"]))) for _ in range(20000)]
        p_cap = sum(math.exp(mu + r) >= CAP for r in E["resid"]) / len(E["resid"])
        per_req.append({"cond": cond, "pool": s["unit"], "n_fragments": nfr, "prompt_chars": len(s["prompt"]),
                        "in_tok": in_tok, "out_med": math.exp(mu), "out_mean": st.fmean(draws),
                        "draws": draws, "p_rbnc": p_cap})
    report = []
    w = report.append
    w("# POST-HOC EXPLORATORY — CONTROLLED EXCERPT GRANULARITY EXPERIMENT: design and price report")
    w("")
    w("RUN_DECISIONS D15. **Design only: nothing has been submitted.** Spec `runs/xgran_J.json` (20 requests: 10 "
      "pools × 2 conditions), marked NOT_SUBMITTED.")
    w("")
    w("## Selected documents, pools and excerpts")
    w("")
    w("| pool | document | corpus set | excerpt words | sentences | sentence frags | token frags | start sentence |")
    w("|---|---|---|---|---|---|---|---|")
    for pid, members in pools:
        for rid in members:
            e = ex[rid]
            where = "headline" if rid in head else "grid" if rid in grid else "held out"
            w(f"| {pid} | {rid} | {where} | {e['words']} | {e['n_sentences']} | {e['n_sentences']} | "
              f"{e['words']} | {e['start_sentence'] + 1} of {e['n_doc_sentences']} |")
    w("")
    w("## Per pool")
    w("")
    w("| pool | sentence frags | token frags | vs 280 target | est. input tok (sentence / token) | "
      "median output tok (sentence / token) | P(128k), token |")
    w("|---|---|---|---|---|---|---|")
    flagged = []
    for pid, members in pools:
        sr = next(r for r in per_req if r["pool"] == pid and r["cond"] == "sentence")
        tr = next(r for r in per_req if r["pool"] == pid and r["cond"] == "token")
        dev = (tr["n_fragments"] - 280) / 280
        if abs(dev) > 0.20:
            flagged.append((pid, tr["n_fragments"]))
        w(f"| {pid} | {sr['n_fragments']} | {tr['n_fragments']} | {dev:+.0%} | {sr['in_tok']:.0f} / "
          f"{tr['in_tok']:.0f} | {sr['out_med']:.0f} / {tr['out_med']:.0f} | {tr['p_rbnc']:.0%} |")
    tok = [r["n_fragments"] for r in per_req if r["cond"] == "token"]
    sen = [r["n_fragments"] for r in per_req if r["cond"] == "sentence"]
    words = [e["words"] for e in ex.values()]
    w("")
    w(f"Excerpt words per document: min {min(words)}, median {st.median(words)}, max {max(words)} (target 40; "
      f"the last sentence is kept whole). Token fragments per pool: min {min(tok)}, median {st.median(tok)}, "
      f"max {max(tok)}. Sentence fragments per pool: min {min(sen)}, median {st.median(sen)}, max {max(sen)}.")
    w(f"Pools more than 20% from the ~280 target: {flagged or 'none'}.")
    w(f"Corpus sets among the 70: headline {sum(r in head for r in ex)}, grid {sum(r in grid for r in ex)}, "
      f"held out {sum(r not in head and r not in grid for r in ex)} (the selection ignores this).")

    def cost(sel, key):
        return sum(r["in_tok"] / 1e6 * IN_PRICE + r[key] / 1e6 * OUT_PRICE for r in sel)

    tot_draws = []
    for k in range(20000):
        tot_draws.append(sum(r["in_tok"] / 1e6 * IN_PRICE + r["draws"][k] / 1e6 * OUT_PRICE for r in per_req))
    tot_draws.sort()
    S = [r for r in per_req if r["cond"] == "sentence"]
    Tk = [r for r in per_req if r["cond"] == "token"]
    worst = sum(r["in_tok"] / 1e6 * IN_PRICE + CAP / 1e6 * OUT_PRICE for r in per_req)
    w("")
    w("## Price (API credit, batch rate $1 / $5 per M tokens; the ledger's rate)")
    w("")
    w("| | requests | expected | worst case (every request at 128k) |")
    w("|---|---|---|---|")
    w(f"| sentence condition | 10 | ${cost(S, 'out_mean'):.2f} | "
      f"${sum(r['in_tok'] / 1e6 + CAP / 1e6 * OUT_PRICE for r in S):.2f} |")
    w(f"| token condition | 10 | ${cost(Tk, 'out_mean'):.2f} | "
      f"${sum(r['in_tok'] / 1e6 + CAP / 1e6 * OUT_PRICE for r in Tk):.2f} |")
    w(f"| repair round (~12%, the final run's J rate) | — | ${0.12 * cost(per_req, 'out_mean'):.2f} | — |")
    w(f"| **total** | 20 | **${1.12 * cost(per_req, 'out_mean'):.2f}** (P95 ${1.12 * tot_draws[int(0.95 * 20000)]:.2f}) | "
      f"**${worst:.2f}** |")
    w(f"| Memon-inspired + MPNet on both conditions | 40 runs | $0 (local; MPNet ≈ "
      f"{(sum(tok) + sum(sen)) / 22.5 / 60:.0f} min at the measured 22.5 fragments/s) | $0 |")
    w("")
    w("## How the estimates were made, and their limits")
    w(f"- **Input tokens:** a linear fit of billed input tokens on prompt characters over the {E['n_clean']} of our "
      f"{E['n_units']} completed one-shot J answers that needed no repair (a repair adds a second prompt to the "
      f"unit's billed input) (tokens ≈ {E['a_in']:.0f} + {E['b_in']:.3f} × chars). "
      "Token prompts carry one label per word, so their per-character rate is uncertain; input is under 1% of the cost "
      "either way.")
    w(f"- **Output tokens:** a log-log fit of the answering call's output tokens on fragment count over the same "
      f"{E['n_units']} answers (out ≈ e^{E['a']:.2f} × n^{E['b']:.2f}), with each pool's uncertainty drawn from the "
      "fit's empirical residuals and capped at 128k (20,000 draws, seed 42).")
    w(f"- **Historical anchors:** of our one-shot J units with 230–330 fragments, {E['near']['units']} were attempted, "
      f"{E['near']['rbnc']} was a non-completion, {E['near']['answer_ge_100k']} of the completed ones used ≥ 100k "
      f"output tokens, and their median was {E['near']['answer_median']:.0f}. Units with ≤ 40 fragments (the "
      f"sentence condition's scale): {E['small']['units']}, median output {E['small']['answer_median']:.0f}.")
    w("- **The main caveat:** every historical unit had sentence-, clause- or 12-word-window fragments. Single-token "
      "fragments are a new regime: the model may reason more per fragment (more output, higher non-completion risk) or "
      "give up sooner. The fit is the best empirical anchor we have, not a validated model for this regime, so the "
      "worst-case line is the budget to plan against.")
    w("- **Non-completion risk** (per token pool, in the table): the share of the fit's residuals that would push that "
      "pool past 128k. RBNCs are kept as RBNCs under D6, never replaced.")
    open(os.path.join(OUT, "DESIGN_REPORT.md"), "w", encoding="utf-8").write("\n".join(report) + "\n")
    print("\n".join(report))
    print(f"\nspec {SPEC}: {len(spec['requests'])} requests, preflight {pf['checked']} checked / {pf['blocked']} blocked")


if __name__ == "__main__":
    main()
