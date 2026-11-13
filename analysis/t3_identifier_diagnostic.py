"""
t3_identifier_diagnostic.py — why does T3 score below the one-bucket base on
the identifier cell (F1_J 0.002, base 0.100)? Post hoc, exploratory: written
after the tier 3 evaluation result was seen. Reads the reported T3
reconstructions; writes only results/final_t3/IDENTIFIER_DIAGNOSTIC.json.

Hypothesis: the model's same-document score follows field type, not record,
so each predicted group gathers one field (names, SSNs, phones, addresses)
across records, i.e. one fragment per record. A record's field is its
fragment's position in the record's true order (answer key).

For every within-group pair of the reconstruction: same record? same field?
Chance for each = the share among all pairs of the pool.

    python analysis/t3_identifier_diagnostic.py
"""

import itertools
import json
import os
import statistics
import sys
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
sys.stdout.reconfigure(encoding="utf-8")

OUT = os.path.join("results", "final_t3")
CELL = os.path.join("results", "identifier_J", "identifier__field")


def main():
    rec, field = {}, {}
    for line in open(os.path.join(CELL, "prose_answer_key.jsonl"), encoding="utf-8"):
        k = json.loads(line)
        for i, f in enumerate(k["order"]):
            rec[f], field[f] = k["record_id"], i
    text = {json.loads(l)["fragment_id"]: json.loads(l)["text"]
            for l in open(os.path.join(CELL, "prose_fragments.jsonl"), encoding="utf-8")}
    rows = [json.loads(l) for l in open(os.path.join(OUT, "identifierJ", "identifier__field.T3-crossenc.jsonl"),
                                        encoding="utf-8")]
    per_pool = []
    tot = Counter()
    for r in rows:
        groups = r["reconstruction"]
        allf = [f for g in groups for f in g]
        wp = [(a, b) for g in groups for a, b in itertools.combinations(g, 2)]
        ap = list(itertools.combinations(allf, 2))
        c = {"within_pairs": len(wp),
             "within_same_record": sum(rec[a] == rec[b] for a, b in wp),
             "within_same_field": sum(field[a] == field[b] for a, b in wp),
             "all_pairs": len(ap),
             "all_same_record": sum(rec[a] == rec[b] for a, b in ap),
             "all_same_field": sum(field[a] == field[b] for a, b in ap),
             "groups_one_field": sum(len({field[f] for f in g}) == 1 for g in groups if len(g) > 1),
             "groups_all_distinct_records": sum(len({rec[f] for f in g}) == len(g) for g in groups if len(g) > 1),
             "groups_size_gt1": sum(len(g) > 1 for g in groups)}
        tot.update(c)
        per_pool.append({"pool": r["pool"], "n_fragments": r["n_fragments"], "n_docs": r["n_docs"],
                         "group_sizes": sorted((len(g) for g in groups), reverse=True), **c})
    res = {
        "label": "post hoc, exploratory",
        "pools": len(rows),
        "within_group_pairs": tot["within_pairs"],
        "share_same_record_within_groups": tot["within_same_record"] / tot["within_pairs"],
        "share_same_record_all_pairs_chance": tot["all_same_record"] / tot["all_pairs"],
        "share_same_field_within_groups": tot["within_same_field"] / tot["within_pairs"],
        "share_same_field_all_pairs_chance": tot["all_same_field"] / tot["all_pairs"],
        "groups_size_gt1": tot["groups_size_gt1"],
        "groups_single_field": tot["groups_one_field"],
        "groups_all_distinct_records": tot["groups_all_distinct_records"],
        "mean_group_size": statistics.fmean(s for p in per_pool for s in p["group_sizes"]),
        "example_pool": {"pool": rows[0]["pool"],
                         "groups": [[text[f] for f in g] for g in rows[0]["reconstruction"]]},
        "per_pool": per_pool}
    json.dump(res, open(os.path.join(OUT, "IDENTIFIER_DIAGNOSTIC.json"), "w", encoding="utf-8"), indent=2)
    print(json.dumps({k: v for k, v in res.items() if k not in ("per_pool", "example_pool")}, indent=1))


if __name__ == "__main__":
    main()
