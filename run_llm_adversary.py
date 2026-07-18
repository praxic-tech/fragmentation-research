import os, json, time, random, re
from dotenv import load_dotenv
from openai import OpenAI

DATA_DIR = r"C:\Users\Arafat\Desktop\SCRMBL"
load_dotenv(os.path.join(DATA_DIR, "apikey.env"))

client = OpenAI(
    base_url="https://api.groq.com/openai/v1",     # Groq (OpenAI-compatible)
    api_key=os.environ["LLM_API_KEY"],
)
MODEL = "llama-3.3-70b-versatile"                  # Groq model — swap here to sweep models later
PAUSE = 2                                          # Groq allows ~30/min, so only a small pause


def load_jsonl(path):
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def append_jsonl(row, path):
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")


def call_model(prompt, model=MODEL, max_transient=8, json_retries=2):
    """Never returns None. Waits out rate limits and temporary server errors;
    fails loudly on a bad model name or persistently bad JSON."""
    transient, json_fails = 0, 0
    while True:
        try:
            resp = client.chat.completions.create(
                model=model, temperature=0,
                messages=[{"role": "user", "content": prompt}],
            )
        except Exception as e:
            msg = str(e)
            if any(s in msg for s in ("429", "RESOURCE_EXHAUSTED", "503", "500",
                                       "UNAVAILABLE", "overloaded", "high demand")):
                transient += 1
                if transient > max_transient:
                    raise RuntimeError("Too many temporary failures — try later or switch provider.")
                m = re.search(r"retry in ([\d.]+)", msg)
                wait = float(m.group(1)) + 2 if m else min(5 * transient, 30)
                print(f"  temporary error — waiting {wait:.0f}s (attempt {transient})...")
                time.sleep(wait)
                continue
            raise            # anything else (e.g. 404 bad model) — surface it, don't hide it
        reply = resp.choices[0].message.content.strip()
        reply = reply.replace("```json", "").replace("```", "").strip()
        try:
            result = json.loads(reply)
        except json.JSONDecodeError:
            json_fails += 1
            if json_fails > json_retries:
                raise ValueError(f"Model didn't return valid JSON: {reply[:200]}")
            time.sleep(2)
            continue
        time.sleep(PAUSE)
        return result


def guess_order(fragments, model=MODEL):                       # Game O
    alias = {f"item_{i}": frag["fragment_id"] for i, frag in enumerate(fragments)}
    lines = "\n".join(f'item_{i}: {frag["text"]}' for i, frag in enumerate(fragments))
    prompt = (
        "These fragments are the fields of ONE personal record, shuffled. "
        "Put them in their most likely original order.\n\nFragments:\n"
        + lines
        + "\n\nReply ONLY with a JSON list of the item labels in your best order."
    )
    guessed = call_model(prompt, model)
    return [alias.get(x, x) for x in guessed]

def guess_groups(pool, n_records, model=MODEL):                # Game L
    alias = {f"item_{i}": frag["fragment_id"] for i, frag in enumerate(pool)}
    lines = "\n".join(f'item_{i}: {frag["text"]}' for i, frag in enumerate(pool))
    prompt = (
        f"Below are shuffled fragments from {n_records} different personal records. "
        "Each record has 4 fields (name, SSN, account, address). "
        f"Group the fragments back into the {n_records} records they came from.\n\nFragments:\n"
        + lines
        + f"\n\nReply ONLY with a JSON list of {n_records} groups, each a list of the item labels."
    )
    guessed = call_model(prompt, model)
    return [[alias.get(x, x) for x in group] for group in guessed]

def main(pool_size=5, model=MODEL):
    fragments = load_jsonl(os.path.join(DATA_DIR, "fragments.jsonl"))
    by_record = {}
    for f in fragments:
        by_record.setdefault(f["record_id"], []).append(f)
    record_ids = sorted(by_record)

    order_path = os.path.join(DATA_DIR, "llm_ordering_guesses.jsonl")
    group_path = os.path.join(DATA_DIR, "llm_grouping_guesses.jsonl")

    # resume: skip anything already written on a previous run
    done_orders = {r["record_id"] for r in load_jsonl(order_path)}
    done_pools  = {r["pool_id"]   for r in load_jsonl(group_path)}

    # Game O — one ordering guess per record
    for rid in record_ids:
        if rid in done_orders:
            continue
        order = guess_order(by_record[rid], model)
        append_jsonl({"record_id": rid, "guessed_order": order}, order_path)
        print(f"order {rid}: {order}")

    # Game L — grouping over small pools (record_id hidden from the model, pool shuffled)
    random.seed(123)
    for pool_id, start in enumerate(range(0, len(record_ids), pool_size)):
        if pool_id in done_pools:
            continue
        chunk_ids = record_ids[start:start + pool_size]
        pool = [{"fragment_id": f["fragment_id"], "text": f["text"]}
                for rid in chunk_ids for f in by_record[rid]]
        random.shuffle(pool)
        groups = guess_groups(pool, n_records=len(chunk_ids), model=model)
        append_jsonl({"pool_id": pool_id, "guessed_groups": groups}, group_path)
        print(f"pool {pool_id}: {groups}")

    print("\ndone — guesses saved to llm_ordering_guesses.jsonl and llm_grouping_guesses.jsonl")


if __name__ == "__main__":
    main()