"""
answer_store.py — every paid answer, kept, and reused by exact request.

WHY
---
A test run and the real run ask many identical questions: the same document,
cut the same way, masked with the same seed, produces a byte-identical prompt.
A question already answered and paid for must never be paid for twice, and an
answer must never be lost because a later step failed. So every succeeded,
non-empty answer is filed under a key derived from the exact model and prompt,
and any later request with the same key is filled from the store instead of
being submitted.

    key = sha256(model + NUL + prompt)[:32]

Nothing else goes into the key: not the custom_id, the cell tag or the wave,
which differ between a test and a real run even when the question is identical.

A reused answer is the same model's answer to the same prompt -- one sample,
exactly as if the request had been sent again. It carries `reused_from` so the
provenance stays visible, and it costs nothing, so its usage is recorded as 0.

    store = AnswerStore()
    to_send, n_reused = split_by_store(store, spec, reused_path)   # before submit
    ... submit / fetch to_send ...
    harvest(store, spec, [reused_path, results_path])             # after fetch
"""

import hashlib
import io
import json
import os
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DEFAULT_STORE = os.path.join(ROOT, "results", "answer_store.jsonl")

__all__ = ["AnswerStore", "request_key", "harvest", "split_by_store"]


def _now():
    return datetime.now(timezone.utc).isoformat()


def request_key(model, prompt):
    return hashlib.sha256(
        (str(model) + "\x00" + prompt).encode("utf-8")).hexdigest()[:32]


class AnswerStore:
    """Append-only JSONL of answers, keyed by exact request. First answer wins."""

    def __init__(self, path=DEFAULT_STORE):
        self.path = path
        self.rows = {}
        if path and os.path.exists(path):
            with io.open(path, encoding="utf-8") as fh:
                for line in fh:
                    if line.strip():
                        r = json.loads(line)
                        self.rows.setdefault(r["key"], r)

    def __len__(self):
        return len(self.rows)

    def get(self, key):
        return self.rows.get(key)

    def add(self, row):
        if row["key"] in self.rows:
            return False
        self.rows[row["key"]] = row
        if self.path:
            os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
            with io.open(self.path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(row) + "\n")
                fh.flush()
        return True


def _sent_prompt(side):
    return side.get("prompt_sent", side["prompt"])


def harvest(store, spec, results_files):
    """File every succeeded, non-empty answer of a wave. Returns how many were new.

    Errored, expired, canceled and empty results are never filed: they are not
    answers, and filing one would make every later identical request "reuse" a
    hole instead of asking again.
    """
    from batch_submit import _latest_rows
    latest = _latest_rows(results_files)
    added = 0
    for cid, side in spec["sidecar"].items():
        row = latest.get(cid)
        if (not row or row.get("result_type") != "succeeded" or row.get("error")
                or not str(row.get("text", "")).strip() or row.get("reused_from")):
            continue
        model = side.get("model") or spec.get("model")
        prompt = _sent_prompt(side)
        added += store.add({
            "key": request_key(model, prompt), "model": model,
            "prompt_sha": hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:16],
            "text": row["text"], "usage": row.get("usage"),
            "source_tag": spec["tag"], "source_custom_id": cid,
            "stored_at": _now()})
    return added


def split_by_store(store, spec, reused_path):
    """Take already-answered requests out of a spec before it is submitted.

    Their stored answers are written to `reused_path` in the batch-results
    schema, so merge_waves and require_complete treat them exactly like fetched
    answers. Returns (spec with only the requests still to send, n_reused).
    """
    from batch_submit import make_custom_id
    todo, reused = [], []
    for r in spec["requests"]:
        model = r.get("model", spec.get("model"))
        hit = store.get(request_key(model, r["prompt"]))
        if hit is None:
            todo.append(r)
            continue
        reused.append({
            "custom_id": make_custom_id(r["cell"], r["game"], r["unit"]),
            "result_type": "succeeded", "text": hit["text"],
            "usage": {"input_tokens": 0, "output_tokens": 0},
            "reused_from": f"{hit['source_tag']}/{hit['source_custom_id']}",
            "fetched_at": _now()})
    os.makedirs(os.path.dirname(os.path.abspath(reused_path)), exist_ok=True)
    with io.open(reused_path, "w", encoding="utf-8") as fh:
        for row in reused:
            fh.write(json.dumps(row) + "\n")
    return {**spec, "requests": todo}, len(reused)
