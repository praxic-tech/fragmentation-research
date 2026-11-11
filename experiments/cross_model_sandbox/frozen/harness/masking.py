"""
masking.py — fragment ID masking, and the pre-flight that proves it happened.

Fragment IDs look like `prose_0007_frag_012`. That string names the document AND
the position inside it, so a prompt containing raw IDs is a jigsaw with the
coordinates printed on the back of every piece: a model can score a perfect tau
without reading any text. Masking swaps IDs for meaningless labels before the
prompt is built and translates back after the answer returns.

Three things live here, and they are separate on purpose:

    mask_fragment_ids / unmask_*   the masker itself, collision-free
    assert_clean / preflight       a refusal to send a prompt that still leaks
    canary_*                       evidence that the alias order carries nothing

The masker was previously inlined in harness.py, which meant the harness was
masked and the adversary was not. This module is the single implementation both
import.

WHY A PRE-FLIGHT AND NOT JUST CAREFUL CODE
------------------------------------------
Masking failing open is invisible: the run completes, the numbers look strong,
and "strong" is exactly what a leak produces. Step 1 of the run plan is a GATE
for that reason, and the gate is only meaningful if we can also demonstrate that
no prompt slipped past. preflight() counts every prompt it clears, so a run can
assert afterwards that the check actually executed rather than being skipped by
a code path nobody remembered.

RELATIONSHIP TO BUG 12
----------------------
Masking IDs is necessary but not sufficient. Ordering also leaked through the
PRESENTATION ORDER: `enumerate(fragments)` over a file written in true document
order made item_0 fragment 0 regardless of how the IDs were labelled. That is
fixed in adversaries/llm_adversary.py; canary_position_correlation() below is
the regression test for it, and it is checked against the alias sequence rather
than the ID strings precisely because the ID strings were never the whole story.
"""

import random
import re

# ── the patterns a prompt must never contain ─────────────────────────────────
# prose_0007_frag_012  — document and position, the ordering answer in plain text
# f_01326 / r_0331     — identifier corpus fragment and record ids
LEAK_PATTERNS = [
    ("prose fragment id", re.compile(r"prose_\d{3,}_frag_\d{2,}")),
    ("prose record id", re.compile(r"\bprose_\d{3,}\b")),
    ("identifier fragment id", re.compile(r"\bf_\d{4,}\b")),
    ("identifier record id", re.compile(r"\br_\d{3,}\b")),
]

# Set by preflight(), read by preflight_stats(). Module-level so a run can prove
# the check ran without threading a counter through every call site.
_PREFLIGHT = {"checked": 0, "blocked": 0}


class IdLeakError(RuntimeError):
    """A prompt still contained raw fragment or record IDs. Never send it.

    Its own exception type because it must not be swallowed by the generic
    `except Exception` retry paths in the adversary — a transient API error is
    worth retrying, a leaking prompt is worth stopping the run for.
    """


# ── masking ──────────────────────────────────────────────────────────────────

def mask_fragment_ids(fragments, seed=None):
    """Replace fragment IDs with labels drawn from a shuffled permutation.

    Labels are a permutation of exactly len(fragments) distinct strings, so
    masking is COLLISION-FREE by construction. The shuffle is what hides the
    order: the label index carries no positional information about the fragment
    it names.

    The previous implementation drew random.randint(100000, 999999) per
    fragment. Over 900,000 possible labels at 16,524 fragments that is a
    birthday problem — ~128 labels collided, each collision overwrote an id_map
    entry, and unmask_groups then silently dropped those fragments from every
    Game L score. Expected collisions at 200 fragments is 0.02, which is why it
    survived until the corpus grew 80x.

    seed is an explicit random.Random instance, not the global module, so the
    harness seeding the global RNG for its Monte Carlo runs cannot perturb the
    mask and vice versa.

    Returns (masked_fragments, id_map) where id_map is label -> original id.
    """
    labels = [f"m_{i:07d}" for i in range(len(fragments))]
    random.Random(seed).shuffle(labels)

    masked, id_map = [], {}
    for label, f in zip(labels, fragments):
        id_map[label] = f["fragment_id"]
        masked.append({"fragment_id": label, "text": f["text"]})

    if len(id_map) != len(fragments):
        raise AssertionError(
            f"mask collision: {len(fragments)} fragments produced {len(id_map)} "
            "distinct labels. Labels must be a permutation."
        )
    return masked, id_map


def unmask_groups(groups, id_map):
    """Masked grouping -> original IDs. Unknown labels are dropped.

    Dropping is reported by the caller's coverage line, not silently absorbed:
    a label the model invented is a real event and scored/supplied/expected is
    where it has to show up.
    """
    return {gid: [id_map[m] for m in ids if m in id_map] for gid, ids in groups.items()}


def unmask_order(order, id_map):
    """Masked ordering -> original IDs, position preserved."""
    return [id_map[m] for m in order if m in id_map]


# ── pre-flight ───────────────────────────────────────────────────────────────

def find_leaks(text):
    """Every raw ID pattern present in text, as (kind, sample, count)."""
    found = []
    for kind, pattern in LEAK_PATTERNS:
        hits = pattern.findall(text or "")
        if hits:
            found.append((kind, hits[0], len(hits)))
    return found


def assert_clean(text, where="prompt"):
    """Raise IdLeakError if text contains any raw ID. Returns text unchanged."""
    leaks = find_leaks(text)
    if leaks:
        detail = "; ".join(f"{k} e.g. {s!r} x{n}" for k, s, n in leaks)
        raise IdLeakError(
            f"{where} contains raw fragment/record IDs: {detail}. "
            "Fragment IDs name the document and the position, so this prompt "
            "would hand the model the answer. Mask before building the prompt."
        )
    return text


def assert_ids_masked(ids, where="attacker input"):
    """Raise IdLeakError if any fragment ID still names its document/position.

    preflight() guards PROMPTS, which protects attackers that talk to a model
    and nothing else. An OFFLINE attacker never builds a prompt, so it can read
    `prose_0002_frag_000` straight off the input and never trip a single check.

    That is not hypothetical. The n-gram joint attacker scored q = 1.0000 --
    perfect ordering -- at n = 8 on a cell where the statistic produced ZERO
    usable evidence: 6,543 of 6,543 pairs at weight 0, context coverage 0.0%.
    Every ordering was decided by order_cluster's deterministic tie rule, which
    concatenates by smallest member, and sorting `prose_0002_frag_000 <
    ..._frag_001 < ...` IS the answer key. The tie rule is honest -- it is
    documented as evidence-free -- but "evidence-free" only means "arbitrary"
    when the identifiers are arbitrary, and raw fragment IDs are not.

    So every attacker asserts its inputs are masked, model-driven or not.
    """
    bad = [i for i in ids if find_leaks(str(i))]
    if bad:
        raise IdLeakError(
            f"{where} received {len(bad)} raw fragment/record IDs, e.g. "
            f"{bad[0]!r}. Fragment IDs name the document and the position, so "
            "any tie-break, sort, or hash over them leaks the answer key. Call "
            "mask_fragment_ids() before the attacker sees the fragments."
        )
    return ids


def preflight(prompt, where="prompt"):
    """assert_clean, with counters so a run can prove the check executed.

    Call this immediately before every outbound request. A run that reports
    checked=0 did not verify anything, which is a different and worse state than
    a run that reports blocked=0.
    """
    _PREFLIGHT["checked"] += 1
    try:
        return assert_clean(prompt, where=where)
    except IdLeakError:
        _PREFLIGHT["blocked"] += 1
        raise


def preflight_stats():
    return dict(_PREFLIGHT)


def reset_preflight_stats():
    _PREFLIGHT["checked"] = 0
    _PREFLIGHT["blocked"] = 0


def preflight_summary():
    s = preflight_stats()
    if s["checked"] == 0:
        return "  [PREFLIGHT] ran 0 times — the ID leak check did NOT execute"
    return (f"  [PREFLIGHT] {s['checked']} prompts checked, "
            f"{s['blocked']} blocked for raw IDs")


# ── leak canary ──────────────────────────────────────────────────────────────

def canary_position_correlation(fragments, seed=None):
    """Correlation between alias index and true document position.

    The regression test for bug 12. Present the fragments the way the adversary
    does, then ask whether item_0 tends to be fragment 0. Near zero means the
    alias sequence is uninformative; near +1 means a model that echoes the input
    order back scores tau 1.0 without reading anything.

    Returns {"r": float, "n": int, "sequential": bool}.
    """
    shuffled = list(fragments)
    random.Random(seed).shuffle(shuffled)

    true_pos = {f["fragment_id"]: i for i, f in enumerate(fragments)}
    xs = list(range(len(shuffled)))
    ys = [true_pos[f["fragment_id"]] for f in shuffled]
    n = len(xs)
    if n < 2:
        return {"r": 0.0, "n": n, "sequential": False}

    mx, my = sum(xs) / n, sum(ys) / n
    cov = sum((a - mx) * (b - my) for a, b in zip(xs, ys))
    vx = sum((a - mx) ** 2 for a in xs) ** 0.5
    vy = sum((b - my) ** 2 for b in ys) ** 0.5
    r = cov / (vx * vy) if vx and vy else 0.0
    return {"r": r, "n": n, "sequential": ys == sorted(ys)}


def canary_report(fragments, trials=200, threshold=0.10):
    """Run the canary over many seeds and summarise.

    A single trial can correlate highly by chance on a short document, so the
    check that matters is the mean over trials and how often the presentation
    order comes out exactly sequential. Expected sequential rate for n
    fragments is 1/n!, i.e. never for anything but the shortest documents.
    """
    rs, seq = [], 0
    for s in range(trials):
        c = canary_position_correlation(fragments, seed=s)
        rs.append(c["r"])
        seq += int(c["sequential"])
    mean_r = sum(rs) / len(rs)
    return {
        "trials": trials,
        "n_fragments": len(fragments),
        "mean_r": mean_r,
        "max_abs_r": max(abs(x) for x in rs),
        "sequential_count": seq,
        "passed": abs(mean_r) < threshold,
    }
