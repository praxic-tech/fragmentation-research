"""Score one model's headline J rows (PREREGISTRATION.md 2026-11-13). NO MODEL CALLS.

    python -I work/runner/score_api.py SLUG        (SLUG: a sweep model, gemma-4-12b, claude-sonnet-5)

Frozen functions only: batch_game.build_repair_spec / score, joint_game.score_row. Nothing
is re-implemented. What this wrapper adds:

  * units that cannot enter the frozen score (content-filtered, not completed after the
    resend, not run under the cap) are removed from the spec passed to it, and listed;
  * the PRIMARY verdict, the preregistered rule as written: REFUSED if any of the 46 (or 41)
    units has no answer, or any scored row's repair.policy_share > joint_game.POLICY_CAP;
  * the 41-pool sensitivity: the same rows, the spec's build.pools and sidecar without
    pool_009, 011, 041, 056, 062;
  * the rates and costs reported beside every score.

Sonnet and Gemma are read-only: their 46-pool scoring goes to a temporary directory and is
checked against the committed rows; only their 41-pool directories are written.
"""
import contextlib
import copy
import io
import json
import os
import shutil
import statistics as st
import sys
import tempfile

SB = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FROZEN = os.path.join(SB, "frozen")
for _d in ("adversaries", "harness", "analysis"):
    sys.path.insert(0, os.path.join(FROZEN, _d))

import batch_game                                                   # noqa: E402
import joint_game                                                   # noqa: E402
from batch_submit import _latest_rows, failed_ids, make_custom_id   # noqa: E402
from joint_game import build_units, score_row                      # noqa: E402

HEADLINE_SPEC = os.path.join(FROZEN, "runs", "final_headlineJ.json")
EPUB_2025_POOLS = ["pool_009", "pool_011", "pool_041", "pool_056", "pool_062"]
TAG = "final-headlineJ"


def subset(spec, drop_cids=(), drop_pools=()):
    """A copy of a spec without some requests (by custom_id) and/or pools (by pool id)."""
    drop_cids, drop_pools = set(drop_cids), set(drop_pools)
    out = copy.deepcopy(spec)
    keep = {c for c, s in spec["sidecar"].items()
            if c not in drop_cids and s["unit"] not in drop_pools}
    out["requests"] = [r for r in spec["requests"]
                       if make_custom_id(r["cell"], r["game"], r["unit"]) in keep]
    out["sidecar"] = {c: s for c, s in spec["sidecar"].items() if c in keep}
    if drop_pools and "build" in out:
        out["build"]["pools"] = [p for p in out["build"]["pools"] if p[0] not in drop_pools]
    return out


def _ids(path):
    return {json.loads(ln)["custom_id"] for ln in open(path, encoding="utf-8") if ln.strip()} \
        if os.path.exists(path) else set()


def model_setup(slug):
    """-> (budget, raw_dir, base spec, base files, repair spec or None, repair files, sweep?)"""
    spec = json.load(open(HEADLINE_SPEC, encoding="utf-8"))
    if slug == "claude-sonnet-5":
        raw = os.path.join(FROZEN, "results", "batches")
        batch_game.MODEL_MAX_OUTPUT = 128000
        bf = [os.path.join(raw, f"{TAG}.results.jsonl"), os.path.join(raw, f"{TAG}-rs1.results.jsonl")]
        rp = batch_game.build_repair_spec([(spec, bf)], 1, 1, f"{TAG}-r1")
        return 128000, raw, spec, bf, rp, [os.path.join(raw, f"{TAG}-r1.results.jsonl")], False
    raw = os.path.join(SB, "raw", slug)
    if slug == "gemma-4-12b":
        budget, sweep = 128000, False
    else:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import api_runner
        budget, sweep = api_runner.CONFIGS[slug]["budget"], True
    batch_game.MODEL_MAX_OUTPUT = budget

    def files(tag):
        return [p for p in (os.path.join(raw, f"{tag}.results.jsonl"),
                            os.path.join(raw, f"{tag}-rs1.results.jsonl")) if os.path.exists(p)]
    rpp = os.path.join(raw, f"{TAG}-r1.spec.json")
    rp = json.load(open(rpp, encoding="utf-8")) if os.path.exists(rpp) else None
    return budget, raw, spec, files(TAG), rp, files(f"{TAG}-r1"), sweep


def exclusions(raw, spec, files, tag):
    """custom_ids of a wave that cannot enter the frozen score, by reason."""
    cf = _ids(os.path.join(raw, f"{tag}.content_filter.jsonl")) | \
        _ids(os.path.join(raw, f"{tag}-rs1.content_filter.jsonl"))
    nr = _ids(os.path.join(raw, f"{tag}.not_run.jsonl")) | _ids(os.path.join(raw, f"{tag}-rs1.not_run.jsonl"))
    rows = _latest_rows(files) if files else {}
    side = set(spec["sidecar"])
    holes = {c for c in failed_ids(files) if c in side and not batch_game.at_ceiling(rows[c])} if files else set()
    missing = side - set(rows) - cf - nr
    return {"content_filter": sorted(cf & side), "not_run": sorted((nr & side) | missing),
            "not_completed": sorted(holes - cf - nr)}


def _score(waves, out, allow_partial=False):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        verdict = batch_game.score(waves, out, allow_partial=allow_partial)
    return {c: sorted(v) for c, v in verdict.items()}, buf.getvalue()


def means(jpath, pools):
    rows = {r["unit"]: r for r in map(json.loads, open(jpath, encoding="utf-8"))}
    f1, fl, q, per = [], [], [], {}
    for pid, members in pools:
        if pid not in rows:
            continue
        _o, _u, key, truth = build_units(os.path.join(FROZEN, "data", "prose"), 0, len(members), 42,
                                         pools=[(pid, members)], o_docs=[])
        s = score_row(rows[pid], key, truth)
        f1.append(s["joint_f1"]); fl.append(s["j_linkage_f1"]); q.append(s["q"])
        per[pid] = {"F1_J": s["joint_f1"], "F1_L": s["j_linkage_f1"], "q": s["q"]}
    m = {"F1_J": st.fmean(f1), "F1_L": st.fmean(fl), "q": st.fmean(q)} if f1 else {}
    return rows, m, per


def usage_totals(raw, slug, sweep):
    """Tokens and cost: every attempt that returned a response (sweep: attempt logs)."""
    tot = {"input_tokens": 0, "output_tokens": 0, "reasoning_tokens": 0, "cost_usd": 0.0,
           "responses": 0, "transport_attempts": 0, "requests_with_transport_error": 0}
    if sweep:
        hit = set()
        for f in sorted(os.listdir(raw)):
            if not f.endswith(".attempts.jsonl"):
                continue
            for ln in open(os.path.join(raw, f), encoding="utf-8"):
                a = json.loads(ln)
                if a["outcome"] == "response":
                    tot["responses"] += 1
                    for k in ("input_tokens", "output_tokens", "reasoning_tokens"):
                        tot[k] += a.get(k) or 0
                    tot["cost_usd"] += a.get("cost_usd") or 0.0
                elif a["outcome"] == "transport":
                    tot["transport_attempts"] += 1
                    hit.add((f, a["custom_id"]))
        tot["requests_with_transport_error"] = len(hit)
    else:
        for f in sorted(os.listdir(raw)):
            if f.startswith(TAG) and f.endswith(".results.jsonl"):
                for ln in open(os.path.join(raw, f), encoding="utf-8"):
                    r = json.loads(ln)
                    u = r.get("usage") or {}
                    if r.get("result_type") == "succeeded":
                        tot["responses"] += 1
                        tot["input_tokens"] += u.get("input_tokens") or 0
                        tot["output_tokens"] += u.get("output_tokens") or 0
                    else:
                        tot["transport_attempts"] += 1
                        tot["requests_with_transport_error"] += 1
        tot["cost_usd"] = None
    return tot


def one_scope(name, n_units, pools, waves, out_dir, excl_units, keep_dirs):
    """Frozen score + primary rule + secondary for one unit set (46 or 41 pools)."""
    tmp = None
    if not keep_dirs:
        tmp = tempfile.mkdtemp(prefix="score_api_")
        out_dir = os.path.join(tmp, "x")
    verdict, rep = _score(waves, out_dir)
    os.makedirs(out_dir, exist_ok=True)
    jpath = os.path.join(out_dir, "prose", "J.jsonl")
    rows, m, per = means(jpath, pools)
    rbnc = [json.loads(ln) for ln in open(os.path.join(out_dir, "prose", "J.rbnc.jsonl"), encoding="utf-8")]
    pool_ids = [p for p, _ in pools]
    no_answer = sorted(set(pool_ids) - set(rows))
    over = sorted(((u, rows[u]["repair"]["policy_share"]) for u in rows
                   if rows[u]["repair"]["policy_share"] > joint_game.POLICY_CAP), key=lambda x: -x[1])
    refused = bool(no_answer or over)
    ps = [rows[u]["repair"]["policy_share"] for u in rows]
    res = {
        "scope": name, "units": n_units,
        "PRIMARY_verdict": "REFUSED" if refused else "PASS",
        "refusal_reasons": {"units_without_answer": no_answer,
                            "units_over_policy_cap": [{"unit": u, "policy_share": round(s, 4)} for u, s in over]},
        "frozen_gate_output": verdict,
        "answered_units": len(rows), "completion_rate": len(rows) / n_units,
        "d6_units": len(rbnc), "d6_rate": len(rbnc) / n_units,
        "excluded_units": excl_units,
        "invalid_after_repair": sum(1 for r in rows.values() if r["repair"]["forced_finalise"]),
        "invalid_after_repair_rate": (sum(1 for r in rows.values() if r["repair"]["forced_finalise"]) / len(rows))
        if rows else None,
        "mean_policy_share": st.fmean(ps) if ps else None,
        "units_over_cap": len(over),
    }
    if refused:
        res["SECONDARY_answered_units_only"] = m
        sec = out_dir + "_answered_units_only" if keep_dirs else os.path.join(tmp, "y")
        _v2, rep2 = _score(waves, sec, allow_partial=True)
        with open(os.path.join(sec, "REPORT.txt"), "w", encoding="utf-8") as fh:
            fh.write("SECONDARY: answered units only (allow_partial=True). The cell is REFUSED under the "
                     "preregistered rule (units without an answer, or a unit's recorded repair.policy_share "
                     "over joint_game.POLICY_CAP); that refusal is the primary result. See ../PRIMARY_RESULT.md.\n\n"
                     + rep2)
    else:
        res["PRIMARY_means"] = m
    with open(os.path.join(out_dir, "REPORT.txt"), "w", encoding="utf-8") as fh:
        fh.write(f"FROZEN GATE OUTPUT (the frozen batch_game.score report, unchanged). The primary verdict "
                 f"is the preregistered rule applied to the rows: {res['PRIMARY_verdict']}. See "
                 f"../PRIMARY_RESULT.md.\n\n" + rep)
    with open(os.path.join(out_dir, "verdict.json"), "w", encoding="utf-8") as fh:
        json.dump({**res, "per_unit": per,
                   "waves": [[w[0]["tag"], [os.path.basename(f) for f in w[1]]] for w in waves]}, fh, indent=1)
    if tmp:
        committed = None
        if name == "46":
            committed = res
        shutil.rmtree(tmp, ignore_errors=True)
        return res, rows if committed else rows
    return res, rows


def score_model(slug):
    budget, raw, spec, bfiles, rp, rfiles, sweep = model_setup(slug)
    res_dir = os.path.join(SB, "results", slug)
    os.makedirs(res_dir, exist_ok=True)
    bex = exclusions(raw, spec, bfiles, TAG)
    bdrop = set(sum(bex.values(), []))
    waves = [(subset(spec, drop_cids=bdrop), bfiles)]
    rex = {"content_filter": [], "not_run": [], "not_completed": []}
    if rp is not None and rp["requests"]:
        rex = exclusions(raw, rp, rfiles, f"{TAG}-r1")
        waves.append((subset(rp, drop_cids=set(sum(rex.values(), []))), rfiles))
    excl_units = {k: sorted(spec["sidecar"][c]["unit"] for c in v) for k, v in bex.items()}
    excl_units["repair_not_sent_or_not_completed"] = sorted(
        rp["sidecar"][c]["unit"] for c in sum(rex.values(), [])) if rp else []

    pools46 = spec["build"]["pools"]
    pools41 = [p for p in pools46 if p[0] not in EPUB_2025_POOLS]
    waves41 = [(subset(s, drop_pools=EPUB_2025_POOLS), f) for s, f in waves]
    e41 = {k: [u for u in v if u not in EPUB_2025_POOLS] for k, v in excl_units.items()}

    r46, rows46 = one_scope("46", 46, pools46, waves, os.path.join(res_dir, "final_headlineJ"), excl_units,
                            keep_dirs=sweep)
    if not sweep:                         # read-only reference: the rows must equal the committed ones
        ref = (os.path.join(FROZEN, "results", "final", "headlineJ", "prose", "J.jsonl")
               if slug == "claude-sonnet-5" else os.path.join(res_dir, "final_headlineJ", "prose", "J.jsonl"))
        refrows = {r["unit"]: r for r in map(json.loads, open(ref, encoding="utf-8"))}
        assert set(refrows) == set(rows46), "re-scored units differ from the committed rows"
        assert all(refrows[u]["raw_response"] == rows46[u]["raw_response"] for u in rows46), \
            "re-scored answers differ from the committed rows"
    r41, _ = one_scope("41", 41, pools41, waves41, os.path.join(res_dir, "final_headlineJ_41pools"), e41,
                       keep_dirs=True)
    summary = {"slug": slug, "budget": budget, "post_hoc_exploratory": True,
               "usage": usage_totals(raw, slug, sweep), "requests_sent": sum(
                   len(_latest_rows(f)) for _s, fs in waves for f in fs), "pools46": r46, "pools41": r41}
    with open(os.path.join(res_dir, "SUMMARY.json"), "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=1)
    if sweep:
        write_primary_md(slug, summary)
    show = {s: {k: summary[s].get(k) for k in ("PRIMARY_verdict", "PRIMARY_means", "SECONDARY_answered_units_only",
                                               "answered_units", "d6_units", "invalid_after_repair",
                                               "units_over_cap", "mean_policy_share", "frozen_gate_output")}
            for s in ("pools46", "pools41")}
    print(json.dumps({"slug": slug, **show, "usage": summary["usage"]}, indent=1))
    return summary


def write_primary_md(slug, s):
    L = [f"# {slug}: headline Game J, primary result", "",
         "Post-hoc exploratory (PREREGISTRATION.md, 2026-11-13). Primary verdict = the preregistered rule "
         "applied to the scored rows (a unit without an answer, or a unit's recorded `repair.policy_share` "
         "over `joint_game.POLICY_CAP` = 0.25, refuses the cell). The frozen gate's own output is kept in "
         "`final_headlineJ*/verdict.json` as `frozen_gate_output`.", ""]
    for key, label in (("pools46", "46 pools"), ("pools41", "41 pools (without the 5 epub-2025 pools)")):
        r = s[key]
        L += [f"## {label}: {r['PRIMARY_verdict']}", ""]
        if r["PRIMARY_verdict"] == "REFUSED":
            rr = r["refusal_reasons"]
            L.append(f"- units without an answer: {len(rr['units_without_answer'])} {rr['units_without_answer']}")
            L.append(f"- units over the cap: {len(rr['units_over_policy_cap'])} "
                     + ", ".join(f"{x['unit']} {x['policy_share']}" for x in rr["units_over_policy_cap"]))
            m = r["SECONDARY_answered_units_only"]
            if m:
                L.append(f"- SECONDARY, answered units only: F1_J {m['F1_J']:.4f}, F1_L {m['F1_L']:.4f}, "
                         f"q {m['q']:.4f}")
        else:
            m = r["PRIMARY_means"]
            L.append(f"- F1_J {m['F1_J']:.4f}, F1_L {m['F1_L']:.4f}, q {m['q']:.4f}")
        L += [f"- completion {r['answered_units']}/{r['units']}; D6 units {r['d6_units']}; "
              f"invalid after repair {r['invalid_after_repair']}/{r['answered_units']}; mean policy_share "
              f"{(r['mean_policy_share'] or 0):.4f}; units over cap {r['units_over_cap']}",
              f"- excluded before the frozen score: {r['excluded_units']}",
              f"- frozen gate output: {r['frozen_gate_output']}", ""]
    u = s["usage"]
    L += ["## Usage", "", f"- responses {u['responses']}, input tokens {u['input_tokens']}, output tokens "
          f"{u['output_tokens']} (reasoning {u['reasoning_tokens']}), cost ${u['cost_usd']:.4f}",
          f"- transport attempts {u['transport_attempts']}, requests with a transport error "
          f"{u['requests_with_transport_error']} of {s['requests_sent']} rows", ""]
    with open(os.path.join(SB, "results", slug, "PRIMARY_RESULT.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(L))


if __name__ == "__main__":
    score_model(sys.argv[1])
