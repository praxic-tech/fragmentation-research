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

import ast
import hashlib
import inspect
import json
import random
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
# Classifier PRECEDENCE, frozen (D11): SSN pattern -> 10-digit account ->
# street-number address -> name. First FULL match wins; format only.
TYPE_RULES = [("ssn", r"\d{3}-\d{2}-\d{4}"),
              ("account", r"\d{10}"),
              ("address", r"\d+\s+\S.*")]           # no match: name
TIE_SEED = 42
_LINE = re.compile(r"^(m_\d{7}): (.*)$", re.M)


def tie_key(text):
    """Order WITHIN a field type: a seeded hash of the fragment's TEXT only.

    Independent of prompt position, alias labels and their order, record ids,
    fragment ids and ground truth. Same-type fragments never share a record,
    so this order cannot change the score; it exists so that the baseline's
    output is fully specified and reproducible.
    """
    return hashlib.sha256(f"{TIE_SEED}|identifier-schema-baseline|{text}".encode("utf-8")).hexdigest()


def visible_items(prompt):
    """(label, text) exactly as shown to the model."""
    return _LINE.findall(prompt)


def type_from_format(text):
    for kind, rx in TYPE_RULES:
        if re.fullmatch(rx, text.strip()):
            return kind
    return "name"


def schema_order_bucket(prompt):
    """The baseline's answer: one bucket in schema order, from the prompt alone.
    Sort key: (published field-order rank of the inferred type, tie_key(text)).
    The label is carried through to the output and used for nothing else."""
    items = visible_items(prompt)
    ranked = sorted(items, key=lambda item: (SCHEMA.index(type_from_format(item[1])), tie_key(item[1])))
    return [[lab for lab, _text in ranked]]


def main():
    from joint_game import build_units, score_row
    # 1. truth-free by construction: the baseline's code touches no hidden field
    # Scan the CODE only: parse each function and drop its docstring (comments
    # vanish in the AST), so prose explaining what the code avoids -- "ground
    # truth", "record ids" -- cannot trip the check, and code using them must.
    def code_only(f):
        tree = ast.parse(inspect.getsource(f))
        fn = tree.body[0]
        if fn.body and isinstance(fn.body[0], ast.Expr) and isinstance(getattr(fn.body[0], "value", None),
                                                                        ast.Constant):
            fn.body = fn.body[1:] or [ast.Pass()]
        return ast.unparse(tree)
    src = "".join(code_only(f) for f in (visible_items, type_from_format, tie_key, schema_order_bucket))
    banned = [w for w in ("field_type", "answer_key", "record_id", "fragment_id", "alias_map", "truth", "key[",
                          "item[0]", "it[0]", "index(item)", "enumerate")
              if w in src]
    print(f"baseline source reads only the prompt, sorts on type + text hash only: "
          f"{'yes' if not banned else 'NO -- ' + str(banned)}")

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
    rows, dup_pools, invariant = [], 0, True
    for s in spec["sidecar"].values():
        items = visible_items(s["prompt"])
        assert len(items) == s["n_fragments"] == len(s["alias_map"]), s["unit"]
        texts = [t for _l, t in items]
        dup_pools += len(set(texts)) != len(texts)     # a tie the hash could not break
        # Independence from prompt position AND alias labels: shuffle the lines,
        # relabel every alias, rebuild the prompt; the output's TEXT sequence
        # must not move.
        by_label = dict(items)
        base_seq = [by_label[lab] for lab in schema_order_bucket(s["prompt"])[0]]
        rng = random.Random(7)
        fresh = [f"m_{i:07d}" for i in rng.sample(range(10 ** 7), len(items))]
        moved = list(zip(fresh, texts))
        rng.shuffle(moved)
        prompt2 = "\n".join(f"{lab}: {t}" for lab, t in moved)
        by_label2 = dict(moved)
        seq2 = [by_label2[lab] for lab in schema_order_bucket(prompt2)[0]]
        invariant &= seq2 == base_seq and schema_order_bucket(s["prompt"]) == schema_order_bucket(s["prompt"])
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
    print(f"pools with an exact-duplicate text (a tie the hash could not break): {dup_pools} of {len(rows)}")
    print(f"output text sequence unchanged after shuffling prompt lines and relabelling aliases, and "
          f"deterministic on repeat: {invariant}")
    ok = not banned and not wrong and exact and dup_pools == 0 and invariant
    json.dump({"what": "identifier schema-order baseline and its truth-free check (D11)",
               "definition": "one bucket; each field type inferred from format alone with frozen precedence "
                             "SSN -> 10-digit account -> street-number address -> name; types in the published "
                             "order name -> ssn -> account -> address; within a type, ascending "
                             "sha256('42|identifier-schema-baseline|' + text); reads only the prompt",
               "precedence": [k for k, _rx in TYPE_RULES] + ["name"], "tie_seed": TIE_SEED,
               "truth_use": "hidden labels only verify the classifier and score the output; never build it",
               "duplicate_text_pools": dup_pools, "invariant_to_position_and_aliases": invariant,
               "type_rules": TYPE_RULES, "schema": SCHEMA, "source_reads_only_prompt": not banned,
               "classifier_correct": len(ft) - len(wrong), "classifier_total": len(ft),
               "pools": rows, "equals_analytic_every_pool": exact, "PASS": ok},
              open("results/audit/identifier_schema_baseline.json", "w", encoding="utf-8"), indent=1)
    print("CHECK", "PASS" if ok else "FAIL", "-> results/audit/identifier_schema_baseline.json")
    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
