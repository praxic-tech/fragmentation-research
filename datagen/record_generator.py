"""Generate the synthetic identifier corpus.

Record generation is a pure function of (n, seed): records are emitted in index
order, so generate(500) reproduces generate(50) exactly as its first 50 records.
Scaling the corpus up therefore extends it rather than replacing it, and any
result computed on the smaller corpus stays comparable.

Usage:
    python datagen/record_generator.py                    # 50 records (original)
    python datagen/record_generator.py -n 500 \\
        --out corpus_expansion/data/identifier_v2/records.jsonl
"""

import argparse
import json
import os
from faker import Faker

fake = Faker("en_US")
OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "identifier")
DEFAULT_OUT = os.path.join(OUT_DIR, "records.jsonl")

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


def parse_args():
    p = argparse.ArgumentParser(description="Generate the synthetic identifier corpus.")
    p.add_argument("-n", "--count", type=int, default=50, help="number of records")
    p.add_argument("--seed", type=int, default=42,
                   help="Faker seed — keep at 42 so smaller corpora stay prefixes")
    p.add_argument("--out", default=DEFAULT_OUT, help="output records.jsonl")
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    records = generate(args.count, seed=args.seed)
    save_records(records, args.out)
    print(f"generated {len(records)} records -> {args.out}")
    for r in records[:3]:
        print(json.dumps(r))
