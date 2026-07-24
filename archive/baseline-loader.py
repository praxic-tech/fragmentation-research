import json


def load_jsonl(path):
    records = []
    with open(path, "r") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def load_fragments(path="data/fragments.jsonl"):
    """
    Returns: list of fragment dicts: {fragment_id, record_id, text}
    """
    return load_jsonl(path)


def load_answer_key(path="data/answer_key.jsonl"):
    """
    Answer key has the true position + field_type per fragment.
    Returns: dict record_id -> list of fragment_ids ordered by true position
    """
    rows = load_jsonl(path)
    by_record = {}
    for row in rows:
        by_record.setdefault(row["record_id"], []).append(row)

    true_order = {}
    for rec_id, frags in by_record.items():
        frags.sort(key=lambda r: r["position"])
        true_order[rec_id] = [r["fragment_id"] for r in frags]

    return true_order


def group_fragments_by_record(fragments):
    """
    Groups the shuffled fragments by their (given) record_id.
    Returns: dict record_id -> list of fragment_ids (in shuffled/arbitrary order)
    """
    groups = {}
    for frag in fragments:
        groups.setdefault(frag["record_id"], []).append(frag["fragment_id"])
    return groups