import os, json, time, random, re
from dotenv import load_dotenv
from openai import OpenAI

BASE = os.path.dirname(os.path.abspath(__file__))     # relative: the folder this script sits in
load_dotenv(os.path.join(BASE, "apikey.env"))

client = OpenAI(
    base_url="https://api.anthropic.com/v1/",         # Anthropic via OpenAI-compat layer
    api_key=os.environ["LLM_API_KEY"],                # Groq alt: https://api.groq.com/openai/v1
)
MODEL = "claude-sonnet-5"                              # model is a parameter — swap for the sweep
TEMPERATURE = None                                    # sonnet-5 rejects temperature; use 0 for Groq
PAUSE = 1


def load_jsonl(path):
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def append_jsonl(row, path):
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")


def extract_json(text):
    """Pull the first JSON array out of a reply, even if wrapped in prose or fences."""
    text = (text or "").replace("```json", "").replace("```", "").strip()
    start, end = text.find("["), text.rfind("]")
    if start == -1 or end == -1 or end < start:
        raise ValueError(f"No JSON array in reply: {text[:200]}")
    return json.loads(text[start:end + 1])


def call_model(prompt, model=MODEL, max_tokens=4096, max_transient=8, json_retries=2):
    transient, json_fails = 0, 0
    kwargs = {"model": model, "max_tokens": max_tokens,
              "messages": [{"role": "user", "content": prompt}]}
    if TEMPERATURE is not None:
        kwargs["temperature"] = TEMPERATURE
    while True:
        try:
            resp = client.chat.completions.create(**kwargs)
        except Exception as e:
            msg = str(e)
            if any(s in msg for s in ("429", "RESOURCE_EXHAUSTED", "503", "500",
                                       "overloaded", "UNAVAILABLE", "high demand")):
                transient += 1
                if transient > max_transient:
                    raise RuntimeError("Too many temporary failures — try later.")
                m = re.search(r"retry in ([\d.]+)", msg)
                wait = float(m.group(1)) + 2 if m else min(5 * transient, 30)
                print(f"  temporary error — waiting {wait:.0f}s...")
                time.sleep(wait)
                continue
            raise
        reply = resp.choices[0].message.content or ""
        try:
            result = extract_json(reply)
        except Exception:
            json_fails += 1
            if json_fails > json_retries:
                raise ValueError(f"Model didn't return valid JSON: {reply[:300]}")
            time.sleep(2)
            continue
        time.sleep(PAUSE)
        return result


def guess_order(fragments, model=MODEL):                       # Game O
    alias = {f"item_{i}": fr["fragment_id"] for i, fr in enumerate(fragments)}
    lines = "\n".join(f'item_{i}: {fr["text"]}' for i, fr in enumerate(fragments))
    prompt = (
        "These fragments are the fields of ONE personal record, shuffled. "
        "Put them in their most likely original order.\n\nFragments:\n" + lines
        + "\n\nReturn ONLY a JSON array of the item labels in your best order."
    )
    return [alias.get(x, x) for x in call_model(prompt, model)]


def repair_partition(groups, all_ids, group_size=4):
    """Force a valid partition: each fragment appears exactly once."""
    valid, seen, cleaned = set(all_ids), set(), []
    for g in groups:
        ng = [x for x in g if x in valid and x not in seen]
        seen.update(ng)
        if ng:
            cleaned.append(ng)
    missing = [x for x in all_ids if x not in seen]
    for i in range(0, len(missing), group_size):
        cleaned.append(missing[i:i + group_size])
    return cleaned


def guess_groups_global(fragments, n_records, model=MODEL):    # Game L — 50-way, single call
    pool = fragments[:]
    random.shuffle(pool)                                        # no positional leak
    alias = {f"item_{i}": fr["fragment_id"] for i, fr in enumerate(pool)}
    lines = "\n".join(f'item_{i}: {fr["text"]}' for i, fr in enumerate(pool))
    prompt = (
        f"Below are {len(pool)} shuffled fragments from {n_records} different personal records. "
        "Each record has exactly 4 fields: name, SSN, account number, address. "
        f"Group ALL fragments into the {n_records} records they came from. Use every item exactly once."
        "\n\nFragments:\n" + lines
        + f"\n\nReturn ONLY a JSON array of {n_records} arrays, each with 4 item labels. "
          "No explanation, no markdown."
    )
    guessed = call_model(prompt, model, max_tokens=16000)      # big output — 50 groups
    groups = [[alias.get(x, x) for x in g] for g in guessed]
    return repair_partition(groups, [f["fragment_id"] for f in fragments])


def main(model=MODEL):
    fragments = load_jsonl(os.path.join(BASE, "fragments.jsonl"))
    by_record = {}
    for f in fragments:
        by_record.setdefault(f["record_id"], []).append(f)
    record_ids = sorted(by_record)

    order_path = os.path.join(BASE, "llm_ordering_guesses.jsonl")
    group_path = os.path.join(BASE, "llm_grouping_guesses.jsonl")
    done_orders = {r["record_id"] for r in load_jsonl(order_path)}

    # Game O — one ordering guess per record (resumes; skips finished ones)
    for rid in record_ids:
        if rid in done_orders:
            continue
        order = guess_order(by_record[rid], model)
        append_jsonl({"record_id": rid, "guessed_order": order}, order_path)
        print(f"order {rid}: {order}")

    # Game L — ONE global 50-way grouping over all fragments (stolen-database setting)
    if not load_jsonl(group_path):
        print("running 50-way grouping (one big call, give it a moment)...")
        groups = guess_groups_global(fragments, n_records=len(record_ids), model=model)
        append_jsonl({"pool_id": 0, "guessed_groups": groups}, group_path)
        print(f"global grouping: {len(groups)} groups over {len(fragments)} fragments")

    print("\ndone — ordering + 50-way grouping saved.")


if __name__ == "__main__":
    main()
