import json
from itertools import combinations
from scipy.stats import kendalltau
import os
BASE          = os.path.dirname(os.path.abspath(__file__))
ROOT          = os.path.dirname(BASE)
ANSWER_KEY    = os.path.join(ROOT, "data", "identifier", "answer_key.jsonl")
ORDER_GUESSES = os.path.join(ROOT, "results", "llm_ordering_guesses.jsonl")
GROUP_GUESSES = os.path.join(ROOT, "results", "llm_grouping_guesses.jsonl")


def load_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def load_true_order(path):
    by = {}
    for r in load_jsonl(path):
        by.setdefault(r["record_id"], []).append(r)
    return {rid: [x["fragment_id"] for x in sorted(f, key=lambda r: r["position"])]
            for rid, f in by.items()}


def load_true_groups(path):
    g = {}
    for r in load_jsonl(path):
        g.setdefault(r["record_id"], []).append(r["fragment_id"])
    return g


# ── Person B's scoring formulas (copied so numbers line up exactly) ──
def eval_ordering(guessed, true_order):
    true_rank = {fid: i for i, fid in enumerate(true_order)}
    return kendalltau([true_rank[f] for f in guessed], list(range(len(true_order)))).statistic


def pairs_from_groups(groups):
    out = set()
    for ids in groups.values():
        for a, b in combinations(sorted(ids), 2):
            out.add((a, b))
    return out


def eval_linkage(guessed_groups, true_groups):
    gp, tp = pairs_from_groups(guessed_groups), pairs_from_groups(true_groups)
    prec = len(gp & tp) / len(gp) if gp else 0.0
    rec  = len(gp & tp) / len(tp) if tp else 0.0
    f1   = 2*prec*rec / (prec+rec) if (prec+rec) > 0 else 0.0
    return prec, rec, f1


if __name__ == "__main__":
    true_order  = load_true_order(ANSWER_KEY)
    true_groups = load_true_groups(ANSWER_KEY)

    # Game O — average Kendall tau over all records
    taus, skipped = [], 0
    for g in load_jsonl(ORDER_GUESSES):
        rid = g["record_id"]
        if sorted(g["guessed_order"]) != sorted(true_order[rid]):
            skipped += 1                      # model dropped/duplicated an id — skip
            continue
        taus.append(eval_ordering(g["guessed_order"], true_order[rid]))
    avg_tau = sum(taus) / len(taus) if taus else 0.0

    # Game L — flatten all per-pool groups into one dict, then score globally
    combined, k = {}, 0
    for pool in load_jsonl(GROUP_GUESSES):
        for grp in pool["guessed_groups"]:
            combined[k] = grp
            k += 1
    p, r, f1 = eval_linkage(combined, true_groups)

    print("=== LLM adversary (Claude claude-sonnet-5, 50-way linkage) ===")
    print(f"  Game O  avg tau  : {avg_tau:.4f}   ({len(taus)} records scored, {skipped} skipped)")
    print(f"  Game L  precision={p:.4f}  recall={r:.4f}  f1={f1:.4f}")
    print()
    print("  For comparison (from Person B):")
    print(f"  Game O  random ~0.00 | statistical 0.06 | NCD 0.14")
    print(f"  Game L  random ~0.02 | statistical f1 0.0267 | NCD f1 0.0223")
