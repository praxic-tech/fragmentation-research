import json
import os
import random

OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "identifier")   # data/identifier at repo root

FIELDS = ["name", "ssn", "account", "address"]        # fixed order = the "original order"


def load_records(path: str) -> list[dict]:
    with open(path, "r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def cut_records(records: list[dict]):
    """Turn each record into one fragment per field.
    Returns (fragments, answer_key) — two parallel lists of dicts."""
    fragments, answer_key = [], []
    counter = 0
    for rec in records:
        for position, field in enumerate(FIELDS):
            fid = f"f_{counter:05d}"
            counter += 1
            fragments.append({
                "fragment_id": fid,
                "record_id":   rec["record_id"],   # tagged with source record (per the email)
                "text":        rec[field],         # the actual field value
            })
            answer_key.append({
                "fragment_id": fid,
                "record_id":   rec["record_id"],
                "position":    position,           # original order — withheld from the guesser
                "field_type":  field,
            })
    return fragments, answer_key


def save_jsonl(rows: list[dict], path: str) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")


if __name__ == "__main__":
    records = load_records(os.path.join(OUT_DIR, "records.jsonl"))
    fragments, answer_key = cut_records(records)

    random.seed(123)              # reproducible shuffle (different seed than the generator)
    random.shuffle(fragments)     # strip the original order

    save_jsonl(fragments,  os.path.join(OUT_DIR, "fragments.jsonl"))
    save_jsonl(answer_key, os.path.join(OUT_DIR, "answer_key.jsonl"))

    print(f"read {len(records)} records → {len(fragments)} fragments")
    print(f"wrote fragments.jsonl and answer_key.jsonl to {OUT_DIR}")