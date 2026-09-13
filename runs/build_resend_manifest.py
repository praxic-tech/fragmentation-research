"""
build_resend_manifest.py — the immutable record of exactly which requests are
resent after the 2026-09-13 credit exhaustion. No API calls.

Built DIRECTLY from the provider-returned result records
(results/batches/<tag>.results.jsonl, written by fetch as the provider returned
them) -- never by inferring "missing" requests from the planned pool list. Each
resend entry is an actual provider refusal with no token usage and no answer.

CLASSIFICATION. These are provider refusals BEFORE inference, for insufficient
credit ("Your credit balance is too low to access the Anthropic API"). They are
not model non-completions (D6) and not malformed outputs: no inference occurred,
so they are eligible for the protocol's one unchanged operational retry.

Hard assertions -- the script refuses to write the manifest if any fails:
  1. every entry is a provider record with result_type != succeeded whose error
     is the credit refusal, with no usage and no answer text;
  2. every failure in these batches is such a refusal (nothing else is mixed in);
  3. the resend the driver would build equals the manifest, request for request,
     and each resent prompt's SHA-256 equals the original prompt's, byte for byte;
  4. no already-answered request appears;
  5. no 128k non-completion appears (those go to the non-retry section);
  6. no request appears twice;
  7. exactly 6 headline and 42 grid entries.

    python runs/build_resend_manifest.py
"""

import datetime
import hashlib
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
for d in ("adversaries", "harness", "analysis"):
    sys.path.insert(0, os.path.join(ROOT, d))

from batch_game import _attempt, at_ceiling, build_resubmit_spec  # noqa: E402
from batch_submit import DEFAULT_STATE_DIR, make_custom_id, results_path, state_path  # noqa: E402

OUT = "runs/resend_manifest_2026-09-13.json"
BASES = [("headline", "final-headlineJ", "runs/final_headlineJ.json")] + \
        [("grid", f"final-gridJ-w{k}", f"runs/final_gridJ_w{k}.json") for k in (1, 2, 3, 4)] + \
        [("identifier", "final-identifierJ", "runs/final_identifierJ.json")]
CREDIT = "credit balance is too low"
EXPECT = {"headline": 6, "grid": 42, "identifier": 0}


def sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def provider_records(tag):
    """The rows exactly as fetch wrote them from the provider, in file order."""
    with open(results_path(DEFAULT_STATE_DIR, tag), encoding="utf-8") as fh:
        return [json.loads(l) for l in fh if l.strip()]


def main():
    resend, non_retry, repair_candidates = [], [], 0
    seen, counts = set(), {"headline": 0, "grid": 0, "identifier": 0}
    for arm, tag, spec_path in BASES:
        spec = json.load(open(spec_path, encoding="utf-8"))
        batch_id = json.load(open(state_path(DEFAULT_STATE_DIR, tag), encoding="utf-8"))["batch_id"]
        records = provider_records(tag)
        ids = [r["custom_id"] for r in records]
        assert len(ids) == len(set(ids)), f"{tag}: the provider returned a request twice"
        failures = [r for r in records if r.get("result_type") != "succeeded"]
        refusals = [r for r in failures if CREDIT in str(r.get("error"))]
        assert len(refusals) == len(failures), \
            f"{tag}: {len(failures) - len(refusals)} failures are not credit refusals"          # 2
        answered = {r["custom_id"] for r in records
                    if r.get("result_type") == "succeeded" and str(r.get("text", "")).strip()}
        for r in records:
            if at_ceiling(r):
                s = spec["sidecar"][r["custom_id"]]
                non_retry.append({
                    "arm": arm, "game": s["game"], "cell": s["cell"], "pool": s["unit"],
                    "base_tag": tag, "batch_id": batch_id, "custom_id": r["custom_id"],
                    "reason": "resource-bounded non-completion (D6): stop_reason max_tokens at "
                              f"{r['usage']['output_tokens']:,} output tokens. Inference ran and exhausted "
                              "the model's 128k ceiling; never retried.",
                    "output_tokens": r["usage"]["output_tokens"]})
            elif r.get("result_type") == "succeeded" and str(r.get("text", "")).strip():
                a = _attempt(spec["sidecar"][r["custom_id"]], r)
                repair_candidates += bool(a["error"] or not a["valid"])

        rs = build_resubmit_spec(spec, [results_path(DEFAULT_STATE_DIR, tag)], tag + "-rs1")
        resent = {make_custom_id(r["cell"], r["game"], r["unit"]): r for r in rs["requests"]}
        assert set(resent) == {r["custom_id"] for r in refusals}, \
            f"{tag}: the resend the driver would build differs from the provider refusals"      # 3
        for r in refusals:
            cid = r["custom_id"]
            s = spec["sidecar"][cid]
            usage = r.get("usage")
            assert not usage or not any(usage.values()), f"{cid}: has token usage"               # 1
            assert not str(r.get("text", "")).strip() and not r.get("partial_text"), f"{cid}: has an answer"
            assert cid not in answered, f"{cid}: already answered"                               # 4
            assert not at_ceiling(r), f"{cid}: a 128k non-completion"                           # 5
            assert cid not in seen, f"{cid}: appears twice"                                     # 6
            seen.add(cid)
            orig_sha, resend_sha = sha(s["prompt"]), sha(resent[cid]["prompt"])
            assert orig_sha == resend_sha, f"{cid}: resent prompt differs from the original"   # 3
            m = re.search(r"request_id='([^']+)'", str(r.get("error")))
            msg = re.search(r"message='([^']+)'", str(r.get("error")))
            resend.append({
                "arm": arm, "game": s["game"], "cell": s["cell"], "pool": s["unit"],
                "base_tag": tag, "batch_id": batch_id, "custom_id": cid,
                "provider_request_id": m.group(1) if m else None,
                "result_type": r.get("result_type"),
                "failure_reason": msg.group(1) if msg else str(r.get("error"))[:200],
                "classification": "provider refusal before inference: insufficient credit",
                "token_usage": usage or None, "answer": None,
                "original_prompt_sha256": orig_sha, "resend_prompt_sha256": resend_sha})
            counts[arm] += 1
    assert counts == EXPECT, f"counts {counts} != {EXPECT}"                                      # 7
    manifest = {
        "what": "resend manifest after the 2026-09-13 credit exhaustion (RUN_DECISIONS D12)",
        "built_from": "provider-returned result records (results/batches/<tag>.results.jsonl), "
                      "not inferred from the planned pool list",
        "classification": "provider refusals BEFORE inference for insufficient credit; not model "
                          "non-completions (D6), not malformed outputs. No inference occurred, so each "
                          "is eligible for the protocol's one unchanged operational retry.",
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "counts": {**counts, "total": len(resend), "non_retry": len(non_retry)},
        "assertions": {"all_entries_are_provider_credit_refusals": True,
                       "every_failure_is_a_credit_refusal": True,
                       "resend_equals_refusals_and_prompt_hashes_match": True,
                       "no_answered_request": True, "no_128k_non_completion": True,
                       "no_duplicates": True, "counts_6_headline_42_grid": True},
        "resend": resend,
        "non_retry": non_retry,
        "repair_round_candidates_among_current_answers": repair_candidates,
    }
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=1)
    print(f"manifest: {len(resend)} resend entries ({counts['headline']} headline, {counts['grid']} grid), "
          f"{len(non_retry)} non-retry; all 7 assertions passed -> {OUT}")
    for n in non_retry:
        print(f"  non-retry: {n['custom_id']} ({n['batch_id']}): {n['output_tokens']:,} output tokens")
    print(f"  provider request ids recorded: {sum(1 for e in resend if e['provider_request_id'])}/{len(resend)}")
    print(f"  (not part of this manifest) current answers that would enter the one repair round: "
          f"{repair_candidates}")


if __name__ == "__main__":
    main()
