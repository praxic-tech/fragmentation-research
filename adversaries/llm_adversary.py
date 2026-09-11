"""
LLM adversary for the fragmentation reassembly games (Part A).

Reads a fragments file and produces two output files consumed by the unified harness:
  - Game O (ordering):  one JSONL line per record with the guessed fragment order
  - Game L (linkage):   one JSONL line with the global grouping in {"groups":{}} schema

Fragment identifiers are masked (item_0, item_1, ...) before the model sees them so
reasoning is based only on text content, never on ID adjacency. Content-agnostic:
works on identifier records and prose (variable fragment counts per record). All paths
are relative to this script. Model name is a CLI argument for the model sweep.

Usage (from the repo root):
    # identifier run (defaults: data/identifier -> results/)
    python adversaries/llm_adversary.py

    # prose run
    python adversaries/llm_adversary.py \\
        --fragments data/prose/prose_fragments.jsonl \\
        --order-out results/prose_llm_ordering_guesses.jsonl \\
        --group-out results/prose_llm_grouping_guesses.jsonl

    # model sweep
    python adversaries/llm_adversary.py --model claude-opus-5
"""

import argparse
import json
import os
import sys
import random
import re
import time

from dotenv import load_dotenv
from openai import OpenAI

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "harness"))
from masking import preflight, preflight_summary   # noqa: E402

BASE_DIR = os.path.dirname(os.path.abspath(__file__))   # adversaries/
ROOT     = os.path.dirname(BASE_DIR)                    # repo root

# ── provider configuration ──────────────────────────────────────────────────────
# Anthropic via the OpenAI-compatible layer.
# To switch to Groq: BASE_URL = "https://api.groq.com/openai/v1"
#                    DEFAULT_MODEL = "llama-3.3-70b-versatile"
#                    DEFAULT_TEMPERATURE = 0.0
PROVIDERS = {
    "anthropic": ("https://api.anthropic.com/v1/", "claude-sonnet-5"),
    "groq":      ("https://api.groq.com/openai/v1", "openai/gpt-oss-120b"),
}
BASE_URL            = "https://api.anthropic.com/v1/"
DEFAULT_MODEL       = "claude-sonnet-5"
DEFAULT_TEMPERATURE = None   # claude-sonnet-5 rejects the temperature parameter
PAUSE_SECONDS       = 1

# ── default paths, anchored to the repo root (all overridable via CLI) ──────────
DEFAULT_FRAGMENTS = os.path.join(ROOT, "data", "identifier", "fragments.jsonl")
DEFAULT_ORDER_OUT = os.path.join(ROOT, "results", "llm_ordering_guesses.jsonl")
DEFAULT_GROUP_OUT = os.path.join(ROOT, "results", "llm_grouping_guesses.jsonl")


def make_client(provider="anthropic"):
    # .env is the file that actually exists at the repo root; apikey.env never
    # did, so load_dotenv was a silent no-op and the bare subscript below raised
    # KeyError before a single request went out. Same fallback as llm_cutter.py.
    load_dotenv(os.path.join(ROOT, ".env"))
    key = (os.environ.get("LLM_API_KEY")
           or os.environ.get("ANTHROPIC_API_KEY")
           or os.environ.get("API_KEY"))
    if not key:
        raise RuntimeError(
            "No API key found. Set LLM_API_KEY, ANTHROPIC_API_KEY or API_KEY "
            "in .env at the repo root."
        )
    base = PROVIDERS.get(provider, (BASE_URL, DEFAULT_MODEL))[0]
    if provider == "groq":
        key = os.environ.get("GROQ_API_KEY") or key
    return OpenAI(base_url=base, api_key=key)


# ── file helpers ────────────────────────────────────────────────────────────────

def load_jsonl(path):
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def append_jsonl(row, path):
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(row) + "\n")


_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.S)


def _longest_array(chunk):
    """The longest span in chunk that a real JSON decoder reads as a list."""
    dec, best, i = json.JSONDecoder(), None, 0
    while True:
        i = chunk.find("[", i)
        if i == -1:
            return best
        try:
            val, end = dec.raw_decode(chunk, i)
        except ValueError:
            i += 1
            continue
        if isinstance(val, list) and (best is None or end - i > best[0]):
            best = (end - i, val)
        i = end


def extract_json_array(text):
    """Return the model's JSON array from a reply that may carry prose or fences.

    A fenced block holding an array is the answer; otherwise the whole reply is
    searched. Either way the LONGEST span a JSON decoder reads as a list wins,
    so a J answer's outer list beats its inner lists and a stray "[1]" in the
    prose cannot pre-empt the real answer.

    The old rule -- first "[" to last "]" -- broke on grid pool 1: a complete
    56-label answer in a ```json fence, preceded by prose containing
    "[35-year-old with ...]", was scored as unparseable.
    """
    text = text or ""
    for chunk in [m.group(1) for m in _FENCE.finditer(text)] + [text]:
        best = _longest_array(chunk)
        if best is not None:
            return best[1]
    raise ValueError(f"No JSON array in reply: {text[:200]}")


# ── model call with retry / backoff ─────────────────────────────────────────────

def call_model(client, prompt, model, temperature=DEFAULT_TEMPERATURE,
               max_tokens=4096, max_transient=8, json_retries=2):
    transient  = 0
    json_fails = 0
    kwargs = {
        "model":      model,
        "max_tokens": max_tokens,
        "messages":   [{"role": "user", "content": prompt}],
    }
    if temperature is not None:
        kwargs["temperature"] = temperature

    while True:
        try:
            response = client.chat.completions.create(**kwargs)
        except Exception as error:
            message          = str(error)
            transient_markers = ("429", "RESOURCE_EXHAUSTED", "503", "500",
                                 "overloaded", "UNAVAILABLE", "high demand")
            if any(marker in message for marker in transient_markers):
                transient += 1
                if transient > max_transient:
                    raise RuntimeError("Too many transient failures — try again later.")
                match = re.search(r"retry in ([\d.]+)", message)
                wait  = float(match.group(1)) + 2 if match else min(5 * transient, 30)
                print(f"  transient error — waiting {wait:.0f}s...")
                time.sleep(wait)
                continue
            raise

        try:
            result = extract_json_array(response.choices[0].message.content or "")
        except Exception:
            json_fails += 1
            if json_fails > json_retries:
                raw = response.choices[0].message.content or ""
                raise ValueError(f"Model did not return valid JSON: {raw[:300]}")
            time.sleep(2)
            continue

        time.sleep(PAUSE_SECONDS)
        return result


# ── Game O: ordering ─────────────────────────────────────────────────────────────

def guess_order(client, fragments, model, temperature=DEFAULT_TEMPERATURE, seed=None):
    """Ask the model to reconstruct the order of one record's fragments.

    BUG 12. The fragments are SHUFFLED before they are aliased. They were not,
    and prose_fragments.jsonl is written in true document order, so item_0 was
    fragment 0 and item_1 was fragment 1 -- while the prompt told the model they
    were shuffled. A model that echoed item_0, item_1, item_2... straight back
    scored tau = 1.0 without reading a word. 23 of the 25 week-4 prose ordering
    guesses are exactly sequential, so that tau was never a measurement of
    reconstruction. guess_groups_global below had shuffled all along, with the
    comment "no positional leak"; it was simply never applied here.

    The shuffle uses an explicit random.Random(seed) instance rather than the
    global module, so a caller seeding the global RNG for its own purposes
    cannot perturb the presentation order, or be perturbed by it.
    """
    shuffled = list(fragments)
    random.Random(seed).shuffle(shuffled)

    alias = {f"item_{i}": frag["fragment_id"] for i, frag in enumerate(shuffled)}
    lines = "\n".join(f'item_{i}: {frag["text"]}' for i, frag in enumerate(shuffled))
    prompt = (
        "These fragments are pieces of ONE record, shuffled. "
        "Put them back in their most likely original order.\n\n"
        "Fragments:\n" + lines +
        "\n\nReturn ONLY a JSON array of the item labels in your best order."
    )
    preflight(prompt, where="guess_order prompt")
    guessed = call_model(client, prompt, model, temperature=temperature)
    return [alias.get(label, label) for label in guessed]


# ── Game L: linkage ──────────────────────────────────────────────────────────────

def repair_partition(groups, all_ids):
    """Force a valid partition for any (variable) group sizes.
    Fragments the model dropped or duplicated become singleton groups."""
    valid   = set(all_ids)
    seen    = set()
    cleaned = []
    for group in groups:
        # `seen` must be updated INSIDE the loop. Building the list first and
        # calling seen.update() afterwards let a fragment repeated within a
        # SINGLE group pass the `not in seen` test twice, so both copies
        # survived and the returned partition was invalid despite this
        # function existing to guarantee it. Cross-group duplicates were caught;
        # same-group ones were not. Found by scoring.check_partition on 3 of 9
        # pools.
        deduped = []
        for x in group:
            if x in valid and x not in seen:
                deduped.append(x)
                seen.add(x)
        if deduped:
            cleaned.append(deduped)
    for fragment_id in all_ids:
        if fragment_id not in seen:
            cleaned.append([fragment_id])
            seen.add(fragment_id)
    return cleaned


def guess_groups_global(client, fragments, n_records, model,
                        temperature=DEFAULT_TEMPERATURE, seed=None):
    pool = fragments[:]
    random.Random(seed).shuffle(pool)   # explicit instance, not the global RNG
    alias = {f"item_{i}": frag["fragment_id"] for i, frag in enumerate(pool)}
    lines = "\n".join(f'item_{i}: {frag["text"]}' for i, frag in enumerate(pool))
    prompt = (
        f"Below are {len(pool)} shuffled fragments from {n_records} different records. "
        "Group them back into the records they came from. Different records may "
        "contain different numbers of fragments. Use every item exactly once.\n\n"
        "Fragments:\n" + lines +
        f"\n\nReturn ONLY a JSON array of {n_records} arrays, each an array of the "
        "item labels that belong to one record. No explanation, no markdown."
    )
    preflight(prompt, where="guess_groups_global prompt")
    # Size the output cap to the answer, do not reserve a flat 16k. Providers
    # count the RESERVATION against tokens-per-minute, so a fixed cap made a
    # pool of three documents fail a rate limit it was nowhere near using: the
    # answer is a few hundred tokens of labels, the reservation was 16,000.
    max_tokens = max(1024, min(16000, len(pool) * 40 + 256))
    guessed    = call_model(client, prompt, model, temperature=temperature,
                            max_tokens=max_tokens)
    translated = [[alias.get(label, label) for label in group] for group in guessed]
    all_ids    = [frag["fragment_id"] for frag in fragments]
    return repair_partition(translated, all_ids)


# ── orchestration ────────────────────────────────────────────────────────────────

def group_by_record(fragments):
    by_record = {}
    for fragment in fragments:
        by_record.setdefault(fragment["record_id"], []).append(fragment)
    return by_record


def run_ordering(client, by_record, record_ids, model, temperature, order_path,
                 seed=None):
    # Count, do not just set-ify: two runs appending to the same file (a resume
    # started while the first process is still alive) produce byte-identical
    # duplicate lines that no value check can detect. Only the count shows it,
    # and a duplicate silently doubles that document's weight in the mean.
    existing = load_jsonl(order_path)
    already_done = {row["record_id"] for row in existing}
    if len(existing) != len(already_done):
        import collections
        dups = {k: v for k, v in
                collections.Counter(r["record_id"] for r in existing).items() if v > 1}
        raise SystemExit(
            f"{order_path} has {len(existing)} lines for {len(already_done)} "
            f"records — duplicates: {dups}\n"
            "  Two runs wrote to this file. Deduplicate it before scoring; the "
            "mean over it is wrong until you do."
        )
    failed = []
    for record_id in record_ids:
        if record_id in already_done:
            continue
        fragments = by_record[record_id]
        try:
            order = guess_order(client, fragments, model, temperature=temperature,
                                seed=seed)
        except Exception as err:
            # One document over the rate-limit ceiling must not take the other
            # ten down with it. Skipped records stay absent from the output file,
            # so a later pass retries them and the coverage line counts them.
            failed.append(record_id)
            print(f"  [skip] {record_id} ({len(fragments)} frags): "
                  f"{str(err)[:110]}")
            continue
        append_jsonl({"record_id": record_id, "guessed_order": order}, order_path)
        print(f"  order {record_id}: {len(fragments)} frags -> guessed")
    _ordering_done(failed, record_ids, already_done)


def _ordering_done(failed, record_ids, already_done):
    n_new = len(record_ids) - len(already_done) - len(failed)
    print(f"  ordering: {n_new} new, {len(already_done)} cached, "
          f"{len(failed)} skipped of {len(record_ids)} documents")
    if failed:
        print(f"  skipped: {', '.join(failed)} — re-run to retry")
    print(preflight_summary())


def run_grouping(client, fragments, n_records, model, temperature, group_path,
                 seed=None, pool_size=None):
    """Game L, either globally or one pool at a time.

    pool_size exists because a whole cell in a single prompt is not answerable:
    calibration showed 10 full-length documents already blowing past 48,000
    output tokens, and a free tier caps a single request far below that. It is
    also what the real run does everywhere — pools of 7, fixed, because pool size
    sets the random floor and a floor that moves between cells makes the cells
    incomparable.

    Each pool is scored as its own observation, so the output is one row per
    pool rather than one row for the cell.
    """
    # Resume per POOL, not per file. Skipping the whole file when it exists was
    # correct while Game L was one global call; with pools it silently freezes a
    # partial run, so a cell that lost three pools to a rate limit could never
    # recover them and would be scored on whatever happened to land.
    existing = load_jsonl(group_path)
    done_pools = {row.get("pool_id") for row in existing}
    if len(existing) != len(done_pools):
        raise SystemExit(
            f"{group_path} has {len(existing)} rows for {len(done_pools)} pools — "
            "duplicates. Deduplicate before scoring."
        )

    by_record = group_by_record(fragments)
    record_ids = sorted(by_record)

    if not pool_size:
        pools = [record_ids]
    else:
        pools = [record_ids[i:i + pool_size]
                 for i in range(0, len(record_ids), pool_size)]

    print(f"running grouping: {len(pools)} pool(s) of up to "
          f"{pool_size or len(record_ids)} documents")
    failed = []
    for pi, members in enumerate(pools):
        if f"pool_{pi:02d}" in done_pools:
            continue
        pool_frags = [f for rid in members for f in by_record[rid]]
        try:
            groups = guess_groups_global(client, pool_frags, len(members), model,
                                         temperature=temperature, seed=seed)
        except Exception as err:
            failed.append(f"pool_{pi:02d}")
            print(f"  [skip] pool_{pi:02d} ({len(pool_frags)} frags): "
                  f"{str(err)[:110]}")
            continue
        append_jsonl({
            "pool_id": f"pool_{pi:02d}",
            "members": members,
            "n_fragments": len(pool_frags),
            "groups": {str(i): g for i, g in enumerate(groups)},
        }, group_path)
        print(f"  pool_{pi:02d}: {len(members)} docs, {len(pool_frags)} frags "
              f"-> {len(groups)} groups")
    print(f"  grouping: {len(pools) - len(failed) - len(done_pools) if False else len(load_jsonl(group_path))}/{len(pools)} pools scored"
          + (f", skipped {', '.join(failed)}" if failed else ""))


def parse_args():
    parser = argparse.ArgumentParser(
        description="LLM adversary for the reassembly games."
    )
    parser.add_argument("--fragments",  default=DEFAULT_FRAGMENTS,
                        help="fragments .jsonl (default: data/identifier/fragments.jsonl)")
    parser.add_argument("--order-out",  default=DEFAULT_ORDER_OUT,
                        help="output file for ordering guesses (.jsonl)")
    parser.add_argument("--group-out",  default=DEFAULT_GROUP_OUT,
                        help="output file for the grouping guess (.jsonl)")
    parser.add_argument("--model",      default=None,
                        help="model name; defaults to the provider's model")
    parser.add_argument("--provider",   default="anthropic", choices=list(PROVIDERS),
                        help="groq is the free-tier option")
    parser.add_argument("--seed",       type=int, default=None,
                        help="seed for the presentation shuffle (bug 12)")
    parser.add_argument("--pool-size", type=int, default=None,
                        help="run Game L per pool of N documents instead of "
                             "one global call; required on a rate-limited tier")
    parser.add_argument("--skip-grouping", action="store_true",
                        help="Game O only — Game L over a whole cell can exceed "
                             "a free tier's tokens-per-minute ceiling")
    return parser.parse_args()


def main():
    args   = parse_args()
    client = make_client(args.provider)
    model  = args.model or PROVIDERS[args.provider][1]

    # CLI paths are taken as given (relative to the current working directory);
    # only the defaults are anchored to the repo root.
    fragments_path = args.fragments
    order_path     = args.order_out
    group_path     = args.group_out

    fragments = load_jsonl(fragments_path)
    if not fragments:
        raise SystemExit(f"No fragments found at {fragments_path}")

    by_record  = group_by_record(fragments)
    record_ids = sorted(by_record)

    print(f"[adversary] provider={args.provider} model={model} "
          f"records={len(record_ids)}")
    run_ordering(client, by_record, record_ids, model, DEFAULT_TEMPERATURE,
                 order_path, seed=args.seed)
    if args.skip_grouping:
        print("\n[Game L skipped]")
    else:
        run_grouping(client, fragments, len(record_ids), model, DEFAULT_TEMPERATURE,
                     group_path, seed=args.seed, pool_size=args.pool_size)

    print("\ndone.")


if __name__ == "__main__":
    main()