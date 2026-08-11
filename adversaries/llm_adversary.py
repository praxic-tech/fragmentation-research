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
import random
import re
import time

from dotenv import load_dotenv
from openai import OpenAI

BASE_DIR = os.path.dirname(os.path.abspath(__file__))   # adversaries/
ROOT     = os.path.dirname(BASE_DIR)                    # repo root

# ── provider configuration ──────────────────────────────────────────────────────
# Anthropic via the OpenAI-compatible layer.
# To switch to Groq: BASE_URL = "https://api.groq.com/openai/v1"
#                    DEFAULT_MODEL = "llama-3.3-70b-versatile"
#                    DEFAULT_TEMPERATURE = 0.0
BASE_URL            = "https://api.anthropic.com/v1/"
DEFAULT_MODEL       = "claude-sonnet-5"
DEFAULT_TEMPERATURE = None   # claude-sonnet-5 rejects the temperature parameter
PAUSE_SECONDS       = 1

# ── default paths, anchored to the repo root (all overridable via CLI) ──────────
DEFAULT_FRAGMENTS = os.path.join(ROOT, "data", "identifier", "fragments.jsonl")
DEFAULT_ORDER_OUT = os.path.join(ROOT, "results", "llm_ordering_guesses.jsonl")
DEFAULT_GROUP_OUT = os.path.join(ROOT, "results", "llm_grouping_guesses.jsonl")


def make_client():
    load_dotenv(os.path.join(ROOT, "apikey.env"))
    return OpenAI(base_url=BASE_URL, api_key=os.environ["LLM_API_KEY"])


# ── file helpers ────────────────────────────────────────────────────────────────

def load_jsonl(path):
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def append_jsonl(row, path):
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(row) + "\n")


def extract_json_array(text):
    """Return the first JSON array found in text, tolerating fences or prose."""
    text = (text or "").replace("```json", "").replace("```", "").strip()
    start, end = text.find("["), text.rfind("]")
    if start == -1 or end == -1 or end < start:
        raise ValueError(f"No JSON array in reply: {text[:200]}")
    return json.loads(text[start:end + 1])


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

def guess_order(client, fragments, model, temperature=DEFAULT_TEMPERATURE):
    alias = {f"item_{i}": frag["fragment_id"] for i, frag in enumerate(fragments)}
    lines = "\n".join(f'item_{i}: {frag["text"]}' for i, frag in enumerate(fragments))
    prompt = (
        "These fragments are pieces of ONE record, shuffled. "
        "Put them back in their most likely original order.\n\n"
        "Fragments:\n" + lines +
        "\n\nReturn ONLY a JSON array of the item labels in your best order."
    )
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
        deduped = [x for x in group if x in valid and x not in seen]
        seen.update(deduped)
        if deduped:
            cleaned.append(deduped)
    for fragment_id in all_ids:
        if fragment_id not in seen:
            cleaned.append([fragment_id])
            seen.add(fragment_id)
    return cleaned


def guess_groups_global(client, fragments, n_records, model,
                        temperature=DEFAULT_TEMPERATURE):
    pool = fragments[:]
    random.shuffle(pool)
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
    guessed    = call_model(client, prompt, model, temperature=temperature,
                            max_tokens=16000)
    translated = [[alias.get(label, label) for label in group] for group in guessed]
    all_ids    = [frag["fragment_id"] for frag in fragments]
    return repair_partition(translated, all_ids)


# ── orchestration ────────────────────────────────────────────────────────────────

def group_by_record(fragments):
    by_record = {}
    for fragment in fragments:
        by_record.setdefault(fragment["record_id"], []).append(fragment)
    return by_record


def run_ordering(client, by_record, record_ids, model, temperature, order_path):
    already_done = {row["record_id"] for row in load_jsonl(order_path)}
    for record_id in record_ids:
        if record_id in already_done:
            continue
        fragments = by_record[record_id]
        order     = guess_order(client, fragments, model, temperature=temperature)
        append_jsonl({"record_id": record_id, "guessed_order": order}, order_path)
        print(f"order {record_id} ({len(fragments)} frags): {order}")


def run_grouping(client, fragments, n_records, model, temperature, group_path):
    if os.path.exists(group_path):
        print(f"grouping already exists ({os.path.basename(group_path)}) — skipping.")
        return
    print("running global grouping (one large call, give it a moment)...")
    groups = guess_groups_global(client, fragments, n_records, model,
                                 temperature=temperature)
    # harness schema: {"groups": {"0": [...], "1": [...], ...}}
    row = {"groups": {str(i): group for i, group in enumerate(groups)}}
    append_jsonl(row, group_path)
    print(f"grouping: {len(groups)} groups over {len(fragments)} fragments "
          f"-> {os.path.basename(group_path)}")


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
    parser.add_argument("--model",      default=DEFAULT_MODEL,
                        help="model name (change for the model sweep)")
    return parser.parse_args()


def main():
    args   = parse_args()
    client = make_client()

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

    run_ordering(client, by_record, record_ids, args.model, DEFAULT_TEMPERATURE,
                 order_path)
    run_grouping(client, fragments, len(record_ids), args.model, DEFAULT_TEMPERATURE,
                 group_path)

    print("\ndone.")


if __name__ == "__main__":
    main()