"""
repair.py — make attack failure distinguishable from serialisation failure.

The pilot measured the model dropping 4-22% of fragments despite being told to
use every item exactly once, and returning duplicates and invented labels. Left
alone that inflates precision (you are only scored on pairs you claimed) and
deflates recall, which is bug 8's signature. But it also confounds the science:
a defence that "wins" because the model could not serialise a large answer is
not a defence, and a reviewer will say so.

So the attacker gets a fixed repair budget, and what happens after the budget is
exhausted is decided here rather than improvised when outputs look bad.

WHAT THE VALIDATOR MAY TELL THE ATTACKER
----------------------------------------
Permitted: which of ITS OWN input labels are missing from ITS OWN output, which
are duplicated, which were invented. That is bookkeeping — a real attacker
computes it with

    missing    = input_ids - output_ids
    duplicates = ids appearing more than once
    invalid    = output_ids - input_ids

from information it already holds. Telling it costs nothing it could not derive.

Forbidden, because these are ground truth the attacker does not have:
    "fragment 17 belongs in cluster 4"
    "you merged two documents"
    "these three fragments are adjacent"
    the document count N, when N was deliberately withheld

EXHAUSTION IS DETERMINISTIC
---------------------------
After the final retry, in this order:
    1. invalid ids (never in the input)      -> discarded
    2. duplicated ids                        -> first occurrence wins
    3. valid ids still unplaced              -> each becomes a singleton group

Singletons are the faithful reading: an attacker who could not place a fragment
claims no pairs for it, so the omission costs recall without inflating
precision. Every action is counted and returned, so the repair is never
invisible in the results.
"""

from collections import Counter

__all__ = ["validate", "finalise", "repair_report_text", "run_with_repair",
           "select_medoid", "pair_agreement"]


# ── validation ───────────────────────────────────────────────────────────────

def validate(groups, all_ids, expected_n=None):
    """Deterministic report on one answer. Uses only the attacker's own view.

    groups     : list of lists of labels, as returned (may be malformed)
    all_ids    : the set of labels the attacker was given
    expected_n : the document count, when the attacker was told it

    expected_n matters more than it looks. Under the primary condition the
    attacker is HANDED N, so "you returned 11 groups, the task specified 7" is
    bookkeeping it could check itself -- not ground truth. Without it an
    all-singleton partition validates as correct, which is wrong twice over: it
    is not a known-N answer, and two all-singleton outputs have empty
    directed-pair sets and therefore agree perfectly with each other, so medoid
    selection would happily pick one.
    """
    flat = [x for g in groups for x in g]
    counts = Counter(flat)
    seen = set(flat)

    invalid = sorted(x for x in seen if x not in all_ids)
    duplicated = sorted(x for x, n in counts.items() if n > 1 and x in all_ids)
    missing = sorted(all_ids - seen)

    n_groups = len(groups)
    group_count_error = (expected_n is not None and n_groups != expected_n)

    return {
        "n_returned": len(flat),
        "n_distinct": len(seen),
        "n_expected": len(all_ids),
        "invalid": invalid,
        "duplicated": duplicated,
        "missing": missing,
        "n_groups": n_groups,
        "expected_n": expected_n,
        "group_count_error": group_count_error,
        "valid": (not invalid and not duplicated and not missing
                  and not group_count_error),
    }


def repair_report_text(report, max_list=40):
    """The message sent back to the attacker. Bookkeeping only, never truth."""
    parts = []
    if report["missing"]:
        ids = report["missing"][:max_list]
        more = "" if len(report["missing"]) <= max_list else \
            f" (and {len(report['missing']) - max_list} more)"
        parts.append(f"These input labels are absent from your answer: "
                     f"{', '.join(ids)}{more}.")
    if report["duplicated"]:
        ids = report["duplicated"][:max_list]
        parts.append(f"These labels appear more than once: {', '.join(ids)}.")
    if report["invalid"]:
        ids = report["invalid"][:max_list]
        parts.append(f"These labels were not in the input: {', '.join(ids)}.")
    if report.get("group_count_error"):
        parts.append(f"You returned {report['n_groups']} groups; the task "
                     f"specifies {report['expected_n']}.")
    if not parts:
        return ""
    return (" ".join(parts) +
            " Return a corrected answer in the same format that uses every "
            "input label exactly once.")


# ── exhaustion ───────────────────────────────────────────────────────────────

def finalise(groups, all_ids):
    """Force a valid partition after the repair budget is spent.

    Order is fixed: discard invalid, first occurrence wins for duplicates, then
    unplaced valid ids become singletons.

    Returns (groups, actions). `actions` is what happened, so scoring can report
    it rather than silently absorbing it.
    """
    seen = set()
    cleaned = []
    discarded_invalid = 0
    dropped_duplicates = 0

    for g in groups:
        keep = []
        for x in g:
            if x not in all_ids:
                discarded_invalid += 1
                continue
            if x in seen:
                dropped_duplicates += 1
                continue
            seen.add(x)
            keep.append(x)
        if keep:
            cleaned.append(keep)

    singletons = sorted(all_ids - seen)
    cleaned.extend([[x] for x in singletons])

    return cleaned, {
        "discarded_invalid": discarded_invalid,
        "dropped_duplicates": dropped_duplicates,
        "singletons_added": len(singletons),
        "final_attempt_coverage": len(seen) / len(all_ids) if all_ids else 0.0,
    }


# ── the loop ─────────────────────────────────────────────────────────────────

def run_with_repair(ask, all_ids, max_retries=2, expected_n=None):
    """Query, validate, request a correction, up to max_retries. Then finalise.

    ask(feedback) -> groups
        feedback is None on the first attempt and a repair message afterwards.
        Raising is treated as a failed attempt and consumes budget.

    Returns (groups, record) where record carries every attempt's validation
    report and the calls spent, because retries are part of the attack cost.
    """
    attempts = []
    groups = []
    feedback = None

    for attempt in range(max_retries + 1):
        try:
            groups = ask(feedback) or []
            error = None
        except Exception as exc:                      # noqa: BLE001
            groups, error = [], f"{type(exc).__name__}: {exc}"

        report = validate(groups, all_ids, expected_n=expected_n)
        attempts.append({"attempt": attempt, "error": error, **{
            k: report[k] for k in
            ("n_returned", "n_distinct", "n_expected", "valid")},
            "n_invalid": len(report["invalid"]),
            "n_duplicated": len(report["duplicated"]),
            "n_missing": len(report["missing"]),
            "n_groups": report["n_groups"],
            "group_count_error": report["group_count_error"]})

        if error is None and report["valid"]:
            break
        feedback = repair_report_text(report)
        if not feedback and error is None:
            break                                     # nothing actionable

    final, actions = finalise(groups, all_ids)
    # Three distinct facts, not one overloaded flag. The old "repaired" was
    # `not attempts[-1]["valid"]`, which reported an answer that FAILED then
    # succeeded on retry as never repaired -- corrupting exactly the compliance
    # statistics used for sizing and reporting, without touching F1.
    return final, {
        "calls": len(attempts),
        "attempts": attempts,
        "repair_attempted": len(attempts) > 1,
        "final_attempt_valid": attempts[-1]["valid"],
        "forced_finalise": not attempts[-1]["valid"],
        "group_count_error": attempts[-1]["group_count_error"],
        **actions,
    }


# ── medoid-of-k selection ────────────────────────────────────────────────────
#
# ONE-SHOT J ONLY. k=3 on the hierarchical attacker would mean three entire
# pipelines -- hundreds of pair-batch calls per pool -- and its internal
# structure gives self-consistency a cheaper home at the pair-score level.
# Forcing one sampling protocol onto attacks with different internals is a
# cost mistake, not a methodological improvement.

def pair_agreement(a, b):
    """Directed-pair F1 between two reconstructions. Uses no ground truth."""
    from joint_metrics import ordered_pairs
    pa, pb = ordered_pairs(a), ordered_pairs(b)
    if not pa and not pb:
        return 1.0
    tp = len(pa & pb)
    if not tp:
        return 0.0
    p, r = tp / len(pa), tp / len(pb)
    return 2 * p * r / (p + r)


def select_medoid(reconstructions):
    """Truth-free best-of-k: the answer most like the others.

    Scored on the FULL directed-pair relation, so grouping and ordering both
    count. Selecting by true score instead would hand the attacker an oracle
    stronger than any we deliberately grant, so it cannot be the primary result.

    Repair must run BEFORE selection: incomplete answers can otherwise win by
    spurious agreement, two sparse answers agreeing trivially because neither
    claims much.

    Returns (index, scores).
    """
    n = len(reconstructions)
    if n == 0:
        return None, []
    if n == 1:
        return 0, [1.0]

    scores = []
    for i, r in enumerate(reconstructions):
        total = sum(pair_agreement(r, o)
                    for j, o in enumerate(reconstructions) if j != i)
        scores.append(total / (n - 1))
    best = max(range(n), key=lambda i: (scores[i], -i))   # deterministic ties
    return best, scores
