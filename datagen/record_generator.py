import json
import os
from faker import Faker

fake = Faker("en_US")
OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "identifier")

def make_record(i: int) -> dict:
    return {
        "record_id": f"r_{i:04d}",
        "name":    f"{fake.first_name()} {fake.last_name()}",
        "ssn":     fake.ssn(),
        "account": fake.numerify("##########"),
        "address": fake.street_address(),
    }


def generate(n: int = 50, seed: int = 42) -> list[dict]:
    Faker.seed(seed)
    return [make_record(i) for i in range(n)]


def save_records(records: list[dict], path: str = "outputs/records.jsonl") -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)   # create folder if missing
    with open(path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")                        # one record per line


if __name__ == "__main__":
    records = generate(50)
    save_records(records, os.path.join(OUT_DIR, "records.jsonl"))
    print(f"generated {len(records)} records → {os.path.join(OUT_DIR, 'records.jsonl')}")
    for r in records[:3]:
        print(json.dumps(r))
