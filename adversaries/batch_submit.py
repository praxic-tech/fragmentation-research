"""
batch_submit.py — Message Batches submission, tagging, and crash-safe retrieval.

Everything in the run goes through the Batches API for the 50% discount. That
buys the discount at the cost of two properties that shape this whole module:

  1. RESULTS COME BACK IN ARBITRARY ORDER. Position is meaningless. The
     custom_id is the only thing that says which cell, game and unit a result
     belongs to. Wave 3 mixes 19 cells plus repeats in a single submission, so
     if a tag is wrong or ambiguous the whole wave is unattributable and the
     money is spent.
  2. THE JOB OUTLIVES THE PROCESS. A batch can take up to 24h. If this script
     dies after create() we have already been billed, so the batch id is
     written to disk BEFORE anything else happens and every fetch is resumable
     against that id. Nothing is ever held only in memory.

Results are appended to JSONL as each one is read, not collected and written at
the end. An interrupted fetch loses nothing it had already seen.

    python adversaries/batch_submit.py --spec runs/step1.json --dry-run
    python adversaries/batch_submit.py --spec runs/step1.json --submit
    python adversaries/batch_submit.py --fetch results/batches/step1.state.json
    python adversaries/batch_submit.py --self-test

A spec is JSON: {"tag": "...", "model": "...", "max_tokens": N,
                 "requests": [{"cell": ..., "game": "O"|"L", "unit": ...,
                               "prompt": "..."}, ...]}
Every prompt is run through harness/masking.py preflight() before it is allowed
into a batch. A prompt still carrying raw fragment IDs aborts the submission
rather than being quietly sent.
"""

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(BASE_DIR)
sys.path.insert(0, os.path.join(ROOT, "harness"))

from masking import (IdLeakError, preflight, preflight_stats,
                     preflight_summary, reset_preflight_stats)
from run_ledger import DEFAULT_MAX_SPEND, Ledger

DEFAULT_MODEL = "claude-sonnet-5"
DEFAULT_MAX_TOKENS = 4096
DEFAULT_STATE_DIR = os.path.join(ROOT, "results", "batches")

# Batch pricing: introductory rates already halved. Matches
# analysis/cost_model_v2.py — the two must not drift apart.
IN_PER_M, OUT_PER_M = 1.0, 5.0

# The API caps custom_id at 64 characters and restricts the alphabet.
CUSTOM_ID_MAX = 64
_CUSTOM_ID_OK = re.compile(r"^[A-Za-z0-9_-]+$")


class ZeroAnswerError(RuntimeError):
    """The call spent its whole output budget on reasoning and returned nothing.

    Billed exactly like a successful call and otherwise indistinguishable from a
    parse failure, which is how it went unnoticed during llm_cutter calibration
    until the spend meter showed money leaving with nothing written. Worth its
    own type so it can be counted separately in the run report.
    """


class SpendMeter:
    """Running token and cost accounting with a hard stop.

    check_budget() is consulted BEFORE each submission using observed mean cost,
    so a cap is never discovered after it has already been passed.
    """

    def __init__(self, budget=None):
        self.budget = budget
        self.in_tok = 0
        self.out_tok = 0
        self.calls = 0

    @property
    def cost(self):
        return self.in_tok / 1e6 * IN_PER_M + self.out_tok / 1e6 * OUT_PER_M

    def record(self, usage):
        if usage is None:
            return
        get = usage.get if isinstance(usage, dict) else lambda k, d=0: getattr(usage, k, d)
        self.in_tok += get("input_tokens", 0) or 0
        self.out_tok += get("output_tokens", 0) or 0
        self.calls += 1

    def would_exceed(self, n_more=1):
        if self.budget is None or self.calls == 0:
            return False
        return self.cost + (self.cost / self.calls) * n_more > self.budget

    def summary(self):
        per = self.cost / self.calls if self.calls else 0.0
        return (f"  spend: ${self.cost:.4f} over {self.calls} results "
                f"(${per:.5f} each)  in {self.in_tok:,} tok / out {self.out_tok:,} tok")


# ── tagging ──────────────────────────────────────────────────────────────────

def make_custom_id(cell, game, unit):
    """cell + game + unit -> a custom_id that survives arbitrary result order.

    Kept human-readable on purpose: when a wave comes back wrong the first thing
    anyone does is read the ids, and an opaque hash makes that impossible.
    """
    # J is the headline game. This check predates the joint threat model, and
    # it meant the paid path could not submit a single J request -- found by
    # the G1 rehearsal on its first request, not by a failed paid batch.
    if game not in ("O", "L", "J"):
        raise ValueError(f"game must be 'O', 'L' or 'J', got {game!r}")
    cid = f"{_slug(cell)}.{game}.{_slug(unit)}".replace(".", "__")
    if len(cid) > CUSTOM_ID_MAX:
        raise ValueError(
            f"custom_id {cid!r} is {len(cid)} chars, over the {CUSTOM_ID_MAX} cap. "
            "Shorten the cell name — the tag has to stay readable."
        )
    if not _CUSTOM_ID_OK.match(cid):
        raise ValueError(f"custom_id {cid!r} has characters outside [A-Za-z0-9_-]")
    return cid


def parse_custom_id(cid):
    parts = cid.split("__")
    if len(parts) != 3:
        raise ValueError(f"cannot parse custom_id {cid!r}")
    return {"cell": parts[0], "game": parts[1], "unit": parts[2]}


def _slug(s):
    return re.sub(r"[^A-Za-z0-9-]+", "-", str(s)).strip("-")


# ── spec -> requests ─────────────────────────────────────────────────────────

def build_requests(spec):
    """Validate a spec and turn it into Batches API request objects.

    Every prompt goes through preflight(). A leaking prompt raises rather than
    being dropped, because a partial batch that silently omits the leaking cells
    is worse than no batch: the gap looks like an API failure later.
    """
    model = spec.get("model", DEFAULT_MODEL)
    max_tokens = spec.get("max_tokens", DEFAULT_MAX_TOKENS)

    requests, seen, unmasked = [], set(), []
    for i, r in enumerate(spec["requests"]):
        for field in ("cell", "game", "unit", "prompt"):
            if field not in r:
                raise ValueError(f"request {i} is missing {field!r}")
        cid = make_custom_id(r["cell"], r["game"], r["unit"])
        if cid in seen:
            raise ValueError(
                f"duplicate custom_id {cid!r}. Results are keyed by id, so a "
                "duplicate means one result silently overwrites another."
            )
        seen.add(cid)

        # The step-1 masking control deliberately sends RAW ids: without an
        # unmasked arm scoring near-perfect, a masked arm scoring low tells you
        # nothing (masking works? or is scoring simply broken?). So the opt-out
        # exists, but it is per-request, explicit in the spec, and counted, so
        # it can never be the silent default.
        if r.get("unmasked_control"):
            unmasked.append(cid)
        else:
            preflight(r["prompt"], where=f"{cid} prompt")

        requests.append({
            "custom_id": cid,
            "params": {
                "model": r.get("model", model),
                "max_tokens": r.get("max_tokens", max_tokens),
                "messages": [{"role": "user", "content": r["prompt"]}],
            },
        })

    if unmasked:
        print(f"  [UNMASKED CONTROL] {len(unmasked)} of {len(requests)} requests "
              f"carry RAW fragment ids by design, e.g. {unmasked[0]}")
        print("  This is the step-1 positive control. If it appears in any other "
              "wave, stop and check the spec.")
    return requests


def estimate_cost(requests, out_tokens_each=None):
    """Rough projection from prompt length. Input only is knowable up front.

    Characters/4 is a deliberate over-estimate for English prose; the point is a
    number to sanity-check a submission against, not an invoice.
    """
    in_tok = sum(len(r["params"]["messages"][0]["content"]) // 4 for r in requests)
    out_tok = sum(out_tokens_each or r["params"]["max_tokens"] for r in requests)
    return {
        "n_requests": len(requests),
        "est_input_tokens": in_tok,
        "est_output_tokens_worst_case": out_tok,
        "est_cost_worst_case": in_tok / 1e6 * IN_PER_M + out_tok / 1e6 * OUT_PER_M,
        "est_cost_input_only": in_tok / 1e6 * IN_PER_M,
    }


# ── state, written before anything is spent ──────────────────────────────────

def state_path(state_dir, tag):
    return os.path.join(state_dir, f"{_slug(tag)}.state.json")


def results_path(state_dir, tag):
    return os.path.join(state_dir, f"{_slug(tag)}.results.jsonl")


def write_state(path, state):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=2)
    os.replace(tmp, path)          # atomic, so a crash mid-write cannot corrupt it
    return path


def read_state(path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def already_fetched(path):
    """custom_ids already on disk, so a resumed fetch does not duplicate them."""
    if not os.path.exists(path):
        return set()
    done = set()
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                try:
                    done.add(json.loads(line)["custom_id"])
                except (json.JSONDecodeError, KeyError):
                    continue
    return done


# ── client ───────────────────────────────────────────────────────────────────

def make_client():
    from dotenv import load_dotenv
    import anthropic
    load_dotenv(os.path.join(ROOT, ".env"))
    key = (os.environ.get("ANTHROPIC_API_KEY")
           or os.environ.get("LLM_API_KEY")
           or os.environ.get("API_KEY"))
    if not key:
        raise RuntimeError(
            "No API key. Set ANTHROPIC_API_KEY, LLM_API_KEY or API_KEY in .env"
        )
    return anthropic.Anthropic(api_key=key)


# ── submit ───────────────────────────────────────────────────────────────────

def submit(spec, state_dir=DEFAULT_STATE_DIR, client=None,
           max_spend=DEFAULT_MAX_SPEND, ledger=None):
    tag = spec["tag"]
    requests = build_requests(spec)
    sp = state_path(state_dir, tag)

    if os.path.exists(sp):
        existing = read_state(sp)
        raise SystemExit(
            f"{sp} already exists (batch {existing.get('batch_id')}). "
            "Fetch it instead of submitting again — resubmitting pays twice."
        )

    client = client or make_client()
    est = estimate_cost(requests)
    print(f"submitting {est['n_requests']} requests, tag {tag!r}")
    print(f"  worst case ${est['est_cost_worst_case']:.2f}, "
          f"input alone ${est['est_cost_input_only']:.2f}")

    # THE SPEND CAP IS CONSULTED HERE, BEFORE create(). With auto-reload on the
    # account balance is no longer a backstop -- a loop that resubmits just buys
    # more credit -- so this is the only real limit. Projected, not observed,
    # because after create() the money is already committed.
    led = ledger if ledger is not None else Ledger(max_spend=max_spend)
    allowed, message = led.check_spend(est["est_cost_worst_case"])
    print(f"  {message}" if allowed else "")
    if not allowed:
        raise SystemExit(message)

    # RESERVE FIRST. If create() succeeds and this process dies before the id
    # is recorded, the ledger must already know money was committed.
    led.reserve(tag, est["est_cost_worst_case"], len(requests))
    try:
        batch = client.messages.batches.create(requests=requests)
    except Exception:
        led.release(tag, est["est_cost_worst_case"], reason="create() failed")
        raise
    led.attach_batch(tag, batch.id)

    # Written FIRST. If the process dies now the batch is still recoverable.
    state = {
        "tag": tag,
        "batch_id": batch.id,
        "submitted_at": datetime.now(timezone.utc).isoformat(),
        "n_requests": len(requests),
        "model": spec.get("model", DEFAULT_MODEL),
        "estimate": est,
        "custom_ids": [r["custom_id"] for r in requests],
        "results_file": os.path.relpath(results_path(state_dir, tag), ROOT).replace("\\", "/"),
    }
    write_state(sp, state)
    print(f"  batch {batch.id}\n  state {sp}")
    return state


# ── fetch ────────────────────────────────────────────────────────────────────

def fetch(state, state_dir=DEFAULT_STATE_DIR, client=None, wait=False,
          poll_seconds=60, meter=None, ledger=None):
    """Stream results to JSONL, appending each as it is read.

    Deliberately not collected in memory and written at the end: a fetch that
    dies at result 2,700 of 2,745 must keep the 2,699 it already has.
    """
    client = client or make_client()
    meter = meter or SpendMeter()
    out = results_path(state_dir, state["tag"])
    done = already_fetched(out)
    if done:
        print(f"  resuming: {len(done)} results already on disk")

    while True:
        batch = client.messages.batches.retrieve(state["batch_id"])
        status = getattr(batch, "processing_status", None)
        if status == "ended":
            break
        if not wait:
            print(f"  batch {state['batch_id']} is {status} — not ready, "
                  "re-run with --wait to block until it ends")
            return {"status": status, "written": 0}
        print(f"  {status} ... waiting {poll_seconds}s")
        time.sleep(poll_seconds)

    counts = {"succeeded": 0, "errored": 0, "zero_answer": 0,
              "expired": 0, "canceled": 0, "skipped": 0}
    written = 0

    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "a", encoding="utf-8") as fh:
        for entry in client.messages.batches.results(state["batch_id"]):
            cid = entry.custom_id
            if cid in done:
                counts["skipped"] += 1
                continue

            row = {"custom_id": cid, **parse_custom_id(cid),
                   "fetched_at": datetime.now(timezone.utc).isoformat()}
            kind = entry.result.type
            row["result_type"] = kind

            if kind == "succeeded":
                msg = entry.result.message
                text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
                usage = {"input_tokens": msg.usage.input_tokens,
                         "output_tokens": msg.usage.output_tokens}
                meter.record(usage)
                row["usage"] = usage
                if not text.strip():
                    # Billed like a success, empty like a failure. Counted, kept.
                    row["error"] = ZeroAnswerError.__name__
                    row["detail"] = (f"empty answer after {usage['output_tokens']} "
                                     "output tokens - all reasoning, no answer")
                    counts["zero_answer"] += 1
                else:
                    row["text"] = text
                    counts["succeeded"] += 1
            else:
                row["error"] = str(getattr(entry.result, "error", kind))
                counts[kind if kind in counts else "errored"] += 1

            fh.write(json.dumps(row) + "\n")
            fh.flush()                 # every result durable before the next is read
            written += 1

    missing = set(state["custom_ids"]) - already_fetched(out)
    unanswered = sorted(set(failed_ids(out)) & set(state["custom_ids"]))
    complete = not missing and not unanswered
    print(f"  wrote {written} results to {out}")
    print(f"  {counts}")
    print(meter.summary())
    if not complete:
        # Was a [WARNING] and a return value nobody checked. An errored,
        # expired or empty result is not an attack outcome, and a result set
        # with holes in it scores clean-looking wrong numbers -- the free-tier
        # grid did exactly that. require_complete() is the gate scoring calls.
        print(f"  [INCOMPLETE] {len(missing)} never came back, "
              f"{len(unanswered)} came back without an answer "
              f"(errored / expired / canceled / empty), "
              f"e.g. {(sorted(missing) + unanswered)[:3]}. "
              "Scoring will refuse this set: resubmit these ids.")
    # Settle once every request has come back, whatever its result type: the
    # batch is finished and its bill is final. Cost is read from the usage
    # stored on disk, not from this process's meter -- a resumed fetch skips
    # rows already written, so its meter only ever sees the tail.
    actual = results_cost(out)
    settled = False
    if ledger is not None and not missing:
        ledger.settle(state["tag"], actual)
        settled = True
    return {"status": "ended", "written": written, "counts": counts,
            "missing": sorted(missing), "unanswered": unanswered,
            "complete": complete, "cost": meter.cost,
            "actual_cost": actual, "settled": settled}


# ── self test ────────────────────────────────────────────────────────────────

def self_test():
    """Exercise tagging, validation and result parsing with no API calls."""
    ok = 0

    cid = make_custom_id("ref_sem_sent", "O", "prose_0042")
    assert cid == "ref-sem-sent__O__prose-0042", cid
    assert parse_custom_id(cid) == {"cell": "ref-sem-sent", "game": "O",
                                    "unit": "prose-0042"}
    print(f"  tag round trip      : {cid}")
    ok += 1

    try:
        make_custom_id("x" * 70, "O", "y")
        raise AssertionError("length cap not enforced")
    except ValueError:
        print("  over-long id        : rejected")
        ok += 1

    reset_preflight_stats()
    spec = {"tag": "t", "requests": [
        {"cell": "c", "game": "O", "unit": "u1", "prompt": "item_0: hello"},
        {"cell": "c", "game": "L", "unit": "u2", "prompt": "item_0: world"},
    ]}
    reqs = build_requests(spec)
    assert len(reqs) == 2
    print(f"  build_requests      : 2 requests, {preflight_summary().strip()}")
    ok += 1

    try:
        build_requests({"tag": "t", "requests": [
            {"cell": "c", "game": "O", "unit": "u", "prompt": "a"},
            {"cell": "c", "game": "O", "unit": "u", "prompt": "b"}]})
        raise AssertionError("duplicate id not caught")
    except ValueError as e:
        print(f"  duplicate id        : rejected ({str(e)[:40]}...)")
        ok += 1

    try:
        build_requests({"tag": "t", "requests": [
            {"cell": "c", "game": "O", "unit": "u",
             "prompt": "prose_0000_frag_003: leaked"}]})
        raise AssertionError("leaking prompt not caught")
    except IdLeakError:
        print("  leaking prompt      : refused before submission")
        ok += 1

    reset_preflight_stats()
    ctrl = build_requests({"tag": "t", "requests": [
        {"cell": "ctrl", "game": "O", "unit": "u", "unmasked_control": True,
         "prompt": "prose_0000_frag_003: deliberately unmasked"}]})
    assert len(ctrl) == 1, "unmasked control request was dropped"
    assert preflight_stats()["checked"] == 0, "flagged request still went to preflight"
    print("  unmasked control    : allowed only with the explicit flag, preflight skipped")
    ok += 1

    m = SpendMeter(budget=0.01)
    m.record({"input_tokens": 1_000_000, "output_tokens": 1_000_000})
    assert abs(m.cost - 6.0) < 1e-9, m.cost
    assert m.would_exceed()
    print(f"  spend meter         : ${m.cost:.2f} on 1M/1M, budget stop fires")
    ok += 1

    est = estimate_cost(reqs)
    print(f"  cost estimate       : {est['n_requests']} reqs, "
          f"worst case ${est['est_cost_worst_case']:.4f}")
    ok += 1

    print(f"\n{ok}/8 self-tests passed (no API calls made)")


# ── cli ──────────────────────────────────────────────────────────────────────

def parse_args():
    ap = argparse.ArgumentParser(description="Submit and retrieve message batches.")
    ap.add_argument("--spec", help="JSON spec file")
    ap.add_argument("--state-dir", default=DEFAULT_STATE_DIR)
    ap.add_argument("--dry-run", action="store_true",
                    help="validate, tag and price the spec without submitting")
    ap.add_argument("--submit", action="store_true", help="create the batch (spends money)")
    ap.add_argument("--fetch", metavar="STATE_JSON", help="retrieve results for a batch")
    ap.add_argument("--wait", action="store_true", help="block until the batch ends")
    ap.add_argument("--poll-seconds", type=int, default=60)
    ap.add_argument("--budget", type=float, default=None)
    ap.add_argument("--max-spend", type=float, default=DEFAULT_MAX_SPEND,
                    help="hard cap on cumulative run spend, checked "
                         "BEFORE each submission against the ledger")
    ap.add_argument("--self-test", action="store_true")
    return ap.parse_args()


def main():
    args = parse_args()

    if args.self_test:
        return self_test()

    if args.fetch:
        return fetch(read_state(args.fetch), state_dir=args.state_dir,
                     wait=args.wait, poll_seconds=args.poll_seconds,
                     meter=SpendMeter(args.budget),
                     ledger=Ledger(max_spend=args.max_spend)) and None

    if not args.spec:
        raise SystemExit("need --spec, --fetch or --self-test")

    spec = json.load(open(args.spec, encoding="utf-8"))
    reset_preflight_stats()

    if args.dry_run or not args.submit:
        reqs = build_requests(spec)
        est = estimate_cost(reqs)
        by_cell = {}
        for r in reqs:
            by_cell.setdefault(parse_custom_id(r["custom_id"])["cell"], 0)
            by_cell[parse_custom_id(r["custom_id"])["cell"]] += 1
        print(f"spec {spec['tag']!r}: {est['n_requests']} requests")
        for cell, n in sorted(by_cell.items()):
            print(f"  {cell:<28} {n:>5}")
        print(f"\n  est input        {est['est_input_tokens']:>12,} tok"
              f"   ${est['est_cost_input_only']:.2f}")
        print(f"  est output (max) {est['est_output_tokens_worst_case']:>12,} tok")
        print(f"  worst case total ${est['est_cost_worst_case']:.2f}")
        print(preflight_summary())
        if not args.submit:
            print("\n  dry run — nothing submitted. Add --submit to spend.")
        return

    submit(spec, state_dir=args.state_dir, max_spend=args.max_spend)


class IncompleteBatchError(RuntimeError):
    """A batch result set with any request missing or unanswered."""


def _latest_rows(out_paths):
    """Latest row per custom_id across one results file or several, in order.

    A resubmitted request comes back in a DIFFERENT batch's results file, so a
    later file's row for the same id supersedes an earlier one.
    """
    if isinstance(out_paths, (str, os.PathLike)):
        out_paths = [out_paths]
    latest = {}
    for out_path in out_paths:
        if os.path.exists(out_path):
            with open(out_path, encoding="utf-8") as fh:
                for line in fh:
                    if line.strip():
                        row = json.loads(line)
                        latest[row["custom_id"]] = row
    return latest


def results_cost(out_paths):
    """Actual spend for results on disk, from the usage stored on each answer.

    Errored and expired requests carry no usage and are not billed.
    """
    cost = 0.0
    for row in _latest_rows(out_paths).values():
        u = row.get("usage") or {}
        cost += (u.get("input_tokens", 0) / 1e6 * IN_PER_M
                 + u.get("output_tokens", 0) / 1e6 * OUT_PER_M)
    return cost


def failed_ids(out_path):
    """custom_ids whose LATEST stored row is not a succeeded, non-empty answer.

    Rows append, so an id that is resubmitted and then succeeds is superseded by
    its newer row and drops out of this list.
    """
    return sorted(cid for cid, row in _latest_rows(out_path).items()
                  if row.get("result_type") != "succeeded" or row.get("error")
                  or not str(row.get("text", "")).strip())


def require_complete(out_path, custom_ids):
    """The gate between a batch and the scorer. Returns {custom_id: row}.

    Raises unless EVERY requested id has a succeeded, non-empty answer. There is
    deliberately no partial mode. An errored or expired request is a hole in the
    sample, the holes are not random -- large prompts fail more -- and a mean over
    the survivors is a different experiment from the one designed.
    """
    latest = _latest_rows(out_path)
    wanted = list(custom_ids)
    missing = [c for c in wanted if c not in latest]
    bad = sorted(set(failed_ids(out_path)) & set(wanted))
    if missing or bad:
        raise IncompleteBatchError(
            f"{len(missing)} of {len(wanted)} requests never came back and "
            f"{len(bad)} came back without an answer, e.g. "
            f"{(missing + bad)[:3]}. Resubmit them; do not score around them.")
    return {c: latest[c] for c in wanted}


if __name__ == "__main__":
    main()
