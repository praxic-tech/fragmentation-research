"""Step 7: the final table of the Sonnet-dependence sweep (post hoc exploratory).

    python -I work/runner/final_table.py   -> results/FINAL_TABLE_sweep_headlineJ.md

Reads only results/<slug>/SUMMARY.json, the attempt/smoke logs and the OpenRouter balance log.
"""
import glob
import json
import os

SB = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
R = os.path.join(SB, "results")


def J(p):
    return json.load(open(p, encoding="utf-8"))


def attempts_cost(paths):
    t = 0.0
    for p in paths:
        for ln in open(p, encoding="utf-8"):
            if ln.strip():
                t += json.loads(ln).get("cost_usd") or 0.0
    return t


SETUP = {
    "claude-sonnet-5": ("Claude Sonnet 5 (reference)", "Anthropic", "Anthropic Message Batches API (frozen primary run)", "128,000"),
    "gpt-5.6-sol": ("gpt-5.6-sol", "OpenAI", "Azure OpenAI, Responses API, service_tier flex, reasoning effort max; DefaultV2 guardrail, the 2 blocked units resent under Default", "128,000"),
    "gpt-4.1": ("gpt-4.1", "OpenAI", "Azure OpenAI, Responses API, tier default; DefaultV2 guardrail", "32,768"),
    "deepseek-v3.2": ("deepseek-v3.2", "DeepSeek", "OpenRouter, GMICloud fp8 only, reasoning enabled", "128,000 (5 rows exceeded it: provider reasoning cap 131,072)"),
    "llama-4-maverick": ("llama-4-maverick", "Meta", "OpenRouter, Parasail fp8 only", "32,768"),
    "gpt-oss-20b": ("gpt-oss-20b", "OpenAI", "OpenRouter, AkashML fp4 only, reasoning effort high, T 1.0, top_p 1.0", "110,000"),
    "gemma-4-12b": ("Gemma 4 12B", "Google", "local: llama.cpp build b12110 + Vulkan, zip SHA-256 9732a5e4...6874f; QAT Q4_0 GGUF", "128,000"),
    "gpt-oss-120b": ("gpt-oss-120b", "OpenAI", "OpenRouter, Parasail fp4 (`parasail/fp4`) only; earlier AkashML fp4 (superseded)", "110,000"),
    "kimi-k2.5": ("kimi-k2.5", "Moonshot AI", "OpenRouter, SiliconFlow int4 (planned)", "128,000 (planned)"),
}
ORDER = ["claude-sonnet-5", "gpt-5.6-sol", "gpt-4.1", "deepseek-v3.2", "llama-4-maverick", "gpt-oss-20b",
         "gemma-4-12b", "gpt-oss-120b", "kimi-k2.5"]
CF = {"gpt-5.6-sol": "2 (pool_005, pool_037; completion side, DefaultV2) -> resent under Default: 2/2 answered"}


def f3(m, sec):
    if not m:
        return "–"
    q = "–" if m.get("q") is None else f"{m['q']:.4f}"
    s = f"{m['F1_J']:.4f} / {m['F1_L']:.4f} / {q}"
    if m.get("n_q_defined") is not None and m.get("n") and m["n_q_defined"] != m["n"]:
        s += f" (q on {m['n_q_defined']}/{m['n']})"
    return f"({s}) *secondary, answered units only*" if sec else s


def scores(r):
    if r["PRIMARY_verdict"] == "PASS":
        return f3(r.get("PRIMARY_means"), False)
    return f3(r.get("SECONDARY_answered_units_only"), True)


def main():
    rows, notes = [], []
    or_recorded = 0.0
    for slug in ORDER:
        name, lab, where, maxout = SETUP[slug]
        p = os.path.join(R, slug, "SUMMARY.json")
        if slug == "kimi-k2.5":
            rows.append([name, lab, where, maxout, "**not run**: planned; dropped for budget under a rule fixed "
                         "before any Kimi request (remaining $5.05 < $7.50)"] + ["–"] * 11)
            continue
        if not os.path.exists(p):           # gpt-oss-120b
            rows.append([name, lab, where, maxout, "**not completed: no pinned provider delivered the 110,000 "
                         "budget**"] + ["–"] * 10 + ["$1.48 recorded + unrecorded in-flight (see below)"])
            continue
        s = J(p)
        a, b, u = s["pools46"], s["pools41"], s["usage"]
        verdict = a["PRIMARY_verdict"] + ("" if a["PRIMARY_verdict"] == b["PRIMARY_verdict"]
                                          else f" (41: {b['PRIMARY_verdict']})")
        if a["PRIMARY_verdict"] == "REFUSED":
            rr = a["refusal_reasons"]
            verdict += (f": {len(rr['units_without_answer'])} without an answer, "
                        f"{len(rr['units_over_policy_cap'])} over the cap")
        n = a["units"]
        tr = (f"{u['requests_with_transport_error']} req ({u['transport_attempts']} attempts); "
              f"not completed {len(a['excluded_units'].get('not_completed', []))}")
        tok = f"in {u['input_tokens']:,} / out {u['output_tokens']:,}" + (
            f" (reasoning {u['reasoning_tokens']:,})" if u.get("reasoning_tokens") else "")
        if slug == "claude-sonnet-5":
            cost = "– (frozen primary run)"
        elif slug == "gemma-4-12b":
            cost = "$0 (local)"
        else:
            cost = f"${u['cost_usd']:.2f}"
            if s.get("total_cost_usd_incl_superseded"):
                cost += f" (+ superseded ${s['superseded_attempts']['cost_usd']:.2f})"
        rows.append([name, lab, where, maxout, verdict, scores(a), scores(b),
                     f"{a['answered_units']}/{n}", str(a["d6_units"]), tr, CF.get(slug, "0"),
                     f"{a['invalid_after_repair']}/{a['answered_units']}",
                     f"{(a['mean_policy_share'] or 0):.4f}", str(a["units_over_cap"]), tok, cost])

    # costs
    az = sum(J(os.path.join(R, s, "SUMMARY.json"))["usage"]["cost_usd"] for s in ("gpt-4.1", "gpt-5.6-sol"))
    sm = [json.loads(x) for x in open(os.path.join(SB, "logs", "smoke_tests.jsonl"), encoding="utf-8") if x.strip()]
    az_smoke = sum(x.get("cost_usd") or 0 for x in sm if x["slug"] in ("gpt-4.1", "gpt-5.6-sol"))
    or_smoke = sum(x.get("cost_usd") or 0 for x in sm if x["slug"] not in ("gpt-4.1", "gpt-5.6-sol"))
    lg = sum(x.get("cost_usd") or 0 for x in sm if x.get("longgen"))
    or_files = [f for s in ("gpt-oss-20b", "gpt-oss-120b", "llama-4-maverick", "deepseek-v3.2")
                for f in glob.glob(os.path.join(SB, "raw", s, "*.attempts.jsonl"))
                + glob.glob(os.path.join(SB, "logs", s, "superseded_*", "*.attempts.jsonl"))]
    or_recorded = attempts_cost(or_files) + or_smoke
    bal = [json.loads(x) for x in open(os.path.join(SB, "logs", "openrouter_balance.jsonl"), encoding="utf-8") if x.strip()]
    usage = bal[-1]["usage"]
    cw = attempts_cost(glob.glob(os.path.join(SB, "logs", "gpt-oss-20b", "superseded_coreweave_*", "*.attempts.jsonl")))
    ak = attempts_cost(glob.glob(os.path.join(SB, "logs", "gpt-oss-120b", "superseded_akashml_*", "*.attempts.jsonl")))
    ps = attempts_cost(glob.glob(os.path.join(SB, "raw", "gpt-oss-120b", "*.attempts.jsonl")))

    H = ["model", "lab", "where it ran", "max output", "verdict (46 pools)", "F1_J / F1_L / q, 46 pools",
         "F1_J / F1_L / q, 41 pools", "completion", "D6", "transport errors", "content-filter blocks",
         "invalid after repair", "mean policy_share", "units over cap", "tokens", "cost"]
    L = ["# Sonnet-dependence sweep on headline Game J: final table", "",
         "**Post hoc exploratory.** PREREGISTRATION.md 2026-11-13 and its amendments (below). Primary verdict "
         "= the preregistered rule applied as written (a unit without an answer after repair, or a unit's "
         "recorded `repair.policy_share` > 0.25, refuses the cell). When REFUSED, the means shown are the "
         "secondary answered-units-only figures, in brackets. Sonnet and Gemma are re-scored read-only with "
         "the same wrapper; frozen/ is byte-identical to its snapshot.", "",
         "| " + " | ".join(H) + " |", "|" + "---|" * len(H)]
    L += ["| " + " | ".join(r) + " |" for r in rows]
    L += ["", "Transport errors: requests with at least one transport error (attempts); not completed = "
          "units still without an answer after the retry limit and the one resend. deepseek-v3.2's were all "
          "stream cut-offs at 30 minutes on the provider route. q is undefined when no linked pairs are guessed "
          "(frozen convention) and left out of the q mean; the count is shown when it differs.", "",
          "## Spend", "",
          f"- **Azure:** ${az:.2f} recorded (gpt-4.1 + gpt-5.6-sol, reported usage x the preregistered rates; "
          f"Flex without cache discount, an upper bound) + smoke tests ${az_smoke:.4f}. Not included: any "
          "tokens Azure billed for the 2 filtered gpt-5.6-sol responses (usage not captured).",
          f"- **OpenRouter (authoritative): key usage ${usage:.4f}** ({bal[-1]['at'][:16]} UTC). Recorded in "
          f"the attempt and smoke logs: ${or_recorded:.4f}; the difference, ${usage - or_recorded:.4f}, is "
          "billing for requests that never reached the attempt log (the gpt-oss-120b requests in flight when "
          "it was stopped; streams cut off by the provider).", "",
          "## Superseded and unscored spend", "",
          f"- gpt-oss-20b on CoreWeave (11 rows + 3 length stops): ${cw:.4f}",
          f"- gpt-oss-120b on AkashML (27 rows + 2 length stops): ${ak:.4f}",
          f"- gpt-oss-120b Parasail long-generation tests (5, inconclusive): ${lg:.4f}",
          f"- gpt-oss-120b Parasail run, stopped at the length stop (13 rows): ${ps:.4f} recorded, plus the "
          "unrecorded in-flight requests (part of the OpenRouter difference above)", "",
          "## Models not run", "",
          "- kimi-k2.5: planned; dropped for budget under the Kimi rule (remaining balance = $10.00 key limit "
          f"- key usage = ${10 - usage:.2f} < $7.50; usage read after models 3-6). No Kimi request was sent.",
          "- From the preregistration: Azure-hosted gpt-oss-120b, DeepSeek-V3.2, Kimi-K2.5, "
          "grok-4-1-fast-reasoning and Llama 4 (not deployable, or zero quota on the student subscription); "
          "gpt-6.x and gpt-5.6-terra/luna (training cutoffs after the documents, or the same family as "
          "gpt-5.6-sol); gpt-5.5 (cost).", "",
          "## Preregistration and amendments", "",
          "- 515571f: preregistration, Sonnet-dependence sweep on headline J (seven hosted models).",
          "- a4ef6ca: amendment 1, gpt-oss on AkashML fp4 with a fixed 110,000 output budget; Azure and "
          "OpenRouter lines concurrent.",
          "- 69c3d8c: amendment 2, Azure content-filter blocks are platform errors, resent once under the "
          "Default guardrail; gpt-oss-120b on Parasail fp4 (cap $3); llama/deepseek in parallel; Kimi balance "
          "defined as limit minus usage.",
          "- User decisions recorded in RUNLOG: gpt-oss-120b's long-generation test replaced by the in-run "
          "check (cc9b943); deepseek-v3.2's over-budget rows accepted as a provider deviation (e02c4d0).", "",
          "## Interpretation (fixed in advance)", "",
          "A model at or above Sonnet (F1_J 0.7225, F1_L 0.8817, q 0.8206) is evidence against Sonnet "
          "dependence of the headline. A lower score is NOT evidence that fragmentation protects, because it "
          "may reflect fit to a Sonnet-tuned prompt.", ""]
    out = os.path.join(R, "FINAL_TABLE_sweep_headlineJ.md")
    open(out, "w", encoding="utf-8").write("\n".join(L))
    print(out)


if __name__ == "__main__":
    main()
