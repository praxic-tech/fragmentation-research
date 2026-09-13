"""
identifier_schema_baseline.py — the identifier SCHEMA-ORDER baseline, and the
check that it is truth-free. No API calls. RUN_DECISIONS D11.

The baseline is an attacker built from NOTHING but what the model is shown plus
public knowledge of the schema:
  1. read the prompt the model receives -- its "label: text" lines, nothing else;
  2. infer each fragment's field type from its FORMAT alone (TYPE_RULES);
  3. put every fragment in ONE bucket, in the generator's published field
     order: name -> ssn -> account -> address. Ties (same type) break on the
     masked label, which is random per unit.
It never reads the answer key, the answer key's field_type labels, record ids or
fragment ids. The verification below uses those hidden labels ONLY to check the
format classifier and the score, never to build the baseline's answer.

    python analysis/identifier_schema_baseline.py
"""

import inspect
import json
import os
import re
import sys
from itertools import combinations

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
os.chdir(ROOT)
for d in ("adversaries", "harness", "analysis"):
    sys.path.insert(0, os.path.join(ROOT, d))

SCHEMA = ["name", "ssn", "account", "address"]      # the published field order
TYPE_RULES = [("ssn", r"\d{3}-\d{2}-\d{4}"),        # format only, full match
              ("account", r"\d{10}"),
              ("address", r"\d+\s+\S.*")]           # anything else: name
_LINE = re.compile(r"^(m_\d{7}): (.*)$", re.M)


def visible_items(prompt):
    """(label, text) exactly as shown to the model."""
    return _LINE.findall(prompt)


def type_from_format(text):
    for kind, rx in TYPE_RULES:
        if re.fullmatch(rx, text.strip()):
            return kind
    return "name"


def schema_order_bucket(prompt):
    """The baseline's answer: one bucket in schema order, from the prompt alone."""
    items = visible_items(prompt)
    return [[lab for lab, txt in sorted(items, key=lambda it: (SCHEMA.index(type_from_format(it[1])), it[0]))]]


def main():
    from joint_game import build_units, score_row
    # 1. truth-free by construction: the baseline's code touches no hidden field
    src = "".join(inspect.getsource(f) for f in (visible_items, type_from_format, schema_order_bucket))
    banned = [w for w in ("field_type", "answer_key", "record_id", "fragment_id", "alias_map", "truth", "key[")
              if w in src]
    print(f"baseline source reads only the prompt: {'yes' if not banned else 'NO -- ' + str(banned)}")

    # 2. the format classifier against the hidden labels (CHECK ONLY), all 2,000 fragments
    ft = {json.loads(l)["fragment_id"]: json.loads(l)["field_type"]
          for l in open("data/identifier/answer_key.jsonl", encoding="utf-8") if l.strip()}
    text = {json.loads(l)["fragment_id"]: json.loads(l)["text"]
            for l in open("data/identifier/fragments.jsonl", encoding="utf-8") if l.strip()}
    wrong = [f for f in ft if type_from_format(text[f]) != ft[f]]
    print(f"format classifier vs hidden field_type (check only): {len(ft) - len(wrong)}/{len(ft)} correct")

    # 3. the baseline on the frozen identifier J prompts, scored by the J scorer
    spec = json.load(open("runs/final_identifierJ.json", encoding="utf-8"))
    b = spec["build"]
    _o, _u, key, truth = build_units(b["cells"][0], 0, 7, 42, pools=b["pools"], o_docs=[])
    rows = []
    for s in spec["sidecar"].values():
        items = visible_items(s["prompt"])
        assert len(items) == s["n_fragments"] == len(s["alias_map"]), s["unit"]
        r = score_row({"game": "J", "unit": s["unit"], "alias_map": s["alias_map"],
                       "raw_response": schema_order_bucket(s["prompt"]),
                       "repair": {"policy_share": 0.0}}, key, truth)
        sizes = [len(v) for v in truth[s["unit"]].values()]
        t = sum(n * (n - 1) // 2 for n in sizes)
        p = s["n_fragments"] * (s["n_fragments"] - 1) // 2
        rows.append({"pool": s["unit"], "schema_joint_f1": r["joint_f1"], "schema_linkage_f1": r["f1"],
                     "schema_q": r["q"], "analytic_schema": 2 * t / (p + t),
                     "analytic_joint_baseline": r["joint_baseline"]})
    exact = all(abs(x["schema_joint_f1"] - x["analytic_schema"]) < 1e-12 for x in rows)
    print(f"schema-order baseline on the {len(rows)} frozen identifier J pools: F1_J "
          f"{min(x['schema_joint_f1'] for x in rows):.4f}-{max(x['schema_joint_f1'] for x in rows):.4f}; "
          f"equals the analytic 2T/(P+T) on every pool: {exact}; q {rows[0]['schema_q']:.3f}; "
          f"analytic joint baseline {rows[0]['analytic_joint_baseline']:.4f}")
    ok = not banned and not wrong and exact
    json.dump({"what": "identifier schema-order baseline and its truth-free check (D11)",
               "definition": "one bucket, fragments ordered by the published field order, each field type "
                             "inferred from its format alone; reads only the prompt",
               "type_rules": TYPE_RULES, "schema": SCHEMA, "source_reads_only_prompt": not banned,
               "classifier_correct": len(ft) - len(wrong), "classifier_total": len(ft),
               "pools": rows, "equals_analytic_every_pool": exact, "PASS": ok},
              open("results/audit/identifier_schema_baseline.json", "w", encoding="utf-8"), indent=1)
    print("CHECK", "PASS" if ok else "FAIL", "-> results/audit/identifier_schema_baseline.json")
    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
