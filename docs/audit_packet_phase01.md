# Audit packet — implemented code, Phases 0 and 1

The **actual code as committed**, extracted from source, not the sketches from
the plan. Commits `a690b66` (Phase 0) and `f14e5cb` (Phase 1).

Everything here is offline: no API calls, no spend. The hierarchical adversary
(Phase 2) is not written yet.

---

## A. Ordered-pair F1, analytic baseline, decomposition, aggregation

`harness/joint_metrics.py`

```python
def ordered_pairs(groups):
    """Every (earlier, later) pair implied by a list of ORDERED groups."""
    out = set()
    for g in groups:
        for i, a in enumerate(g):
            for b in g[i + 1:]:
                out.add((a, b))
    return out

def unordered_pairs(groups):
    """Every co-membership pair, direction discarded."""
    return {frozenset((a, b)) for g in groups for a, b in combinations(g, 2)}

def score_joint(guessed_groups, true_order, members):
    """Ordered-pair precision / recall / F1 for a partition-with-order.

    guessed_groups : list of lists of fragment ids, ordered within each group
    true_order     : {record_id: [fragment ids in true order]}
    members        : record_ids belonging to this pool
    """
    guessed = ordered_pairs(guessed_groups)
    truth = ordered_pairs(_true_groups_as_lists(true_order, members))
    tp = len(guessed & truth)
    p = tp / len(guessed) if guessed else 0.0
    r = tp / len(truth) if truth else 0.0
    return {
        "precision": p,
        "recall": r,
        "f1": 2 * p * r / (p + r) if (p + r) else 0.0,
        "tp": tp,
        "n_guessed": len(guessed),
        "n_true": len(truth),
    }

def analytic_baseline(true_groups):
    """Expected score of one bucket in arbitrary order. Closed form, no sampling.

    true_groups : {record_id: [fragment ids]} — only the SIZES are used.
    Returns {"joint": ..., "linkage": ...} with joint == linkage / 2 exactly.
    """
    sizes = [len(v) for v in true_groups.values()]
    m = sum(sizes)
    t = sum(s * (s - 1) // 2 for s in sizes)
    p = m * (m - 1) // 2
    if p + t == 0:
        return {"joint": 0.0, "linkage": 0.0, "true_pairs": t, "bucket_pairs": p}
    return {
        "joint": t / (p + t),
        "linkage": 2 * t / (p + t),
        "true_pairs": t,
        "bucket_pairs": p,
    }

def advantage(f1, baseline):
    """A = (F1 - baseline) / (1 - baseline). 0 at baseline, 1 at perfect.

    Negative when the attack does worse than one bucket. MUST be computed per
    pool and then averaged: the baseline moves with each pool's fragment-count
    distribution, so normalising grand means is a different quantity.
    """
    denom = 1.0 - baseline
    if denom <= 0:
        return float("nan")
    return (f1 - baseline) / denom

def decompose(guessed_groups, true_order, members):
    """Split joint performance into linkage and conditional direction accuracy.

    Returns, per pool:
        f1_joint, f1_linkage   on the same scale, F1_J = F1_L * q
        C  correctly co-clustered AND correctly directed pairs
        K  correctly co-clustered pairs, direction ignored
        q  C/K, or None when K == 0
        a_joint, a_linkage     baseline-normalised advantages
        a_order                2q - 1, or None when q is None

    q is UNDEFINED when K == 0, and is reported as None rather than 0. Coercing
    it to zero converts "ordering could not be evaluated because linkage failed
    completely" into "ordering was completely wrong", which are different
    findings. Callers aggregate with micro_q() and report the undefined rate.
    """
    truth_lists = _true_groups_as_lists(true_order, members)
    g_ord, t_ord = ordered_pairs(guessed_groups), ordered_pairs(truth_lists)
    g_un, t_un = unordered_pairs(guessed_groups), unordered_pairs(truth_lists)

    c = len(g_ord & t_ord)
    k = len(g_un & t_un)
    denom = len(g_un) + len(t_un)

    f1_joint = 2 * c / denom if denom else 0.0
    f1_link = 2 * k / denom if denom else 0.0

    true_groups = {r: true_order[r] for r in members}
    base = analytic_baseline(true_groups)

    q = (c / k) if k else None
    return {
        "f1_joint": f1_joint,
        "f1_linkage": f1_link,
        "C": c,
        "K": k,
        "q": q,
        "baseline_joint": base["joint"],
        "baseline_linkage": base["linkage"],
        "a_joint": advantage(f1_joint, base["joint"]),
        "a_linkage": advantage(f1_link, base["linkage"]),
        "a_order": (2 * q - 1) if q is not None else None,
        "n_guessed_pairs": len(g_un),
        "n_true_pairs": len(t_un),
    }

def micro_q(rows):
    """Direction accuracy aggregated as sum(C)/sum(K) across pools.

    Returns (q, n_undefined_pools). q is None when sum(K) == 0 over the whole
    collection — which is also the behaviour a bootstrap replicate needs, since
    a resample can legitimately contain only pools where linkage failed.
    """
    total_c = sum(r["C"] for r in rows)
    total_k = sum(r["K"] for r in rows)
    undefined = sum(1 for r in rows if r["K"] == 0)
    return ((total_c / total_k) if total_k else None), undefined

def paired_bootstrap_indices(n_pools, n_replicates, rng):
    """Pool indices for a PAIRED bootstrap, one index vector per replicate.

    Every strategy and every attacker must be resampled with the SAME indices
    within a replicate. The shared-pool grid exists to buy that pairing, and
    resampling each cell independently throws it away — silently, since the
    output still looks like a distribution.

    Yielding the indices rather than the resampled data keeps the sharing
    structural: a caller cannot accidentally draw a second time.
    """
    for _ in range(n_replicates):
        yield [int(i) for i in rng.integers(0, n_pools, size=n_pools)]
```

**Please check:** the three identities hold as implemented; `advantage` is applied per pool and never to grand means; `micro_q` returning None on sum(K)=0 is the behaviour you intended for a bootstrap replicate.

---

## B. Repair: validation, permitted feedback, deterministic exhaustion

`harness/repair.py`

```python
def validate(groups, all_ids):
    """Deterministic report on one answer. Uses only the attacker's own view.

    groups  : list of lists of labels, as returned (may be malformed)
    all_ids : the set of labels the attacker was given

    Returns counts plus the actual id lists, so a caller can build a repair
    message without recomputing anything.
    """
    flat = [x for g in groups for x in g]
    counts = Counter(flat)
    seen = set(flat)

    invalid = sorted(x for x in seen if x not in all_ids)
    duplicated = sorted(x for x, n in counts.items() if n > 1 and x in all_ids)
    missing = sorted(all_ids - seen)

    return {
        "n_returned": len(flat),
        "n_distinct": len(seen),
        "n_expected": len(all_ids),
        "invalid": invalid,
        "duplicated": duplicated,
        "missing": missing,
        "valid": not invalid and not duplicated and not missing,
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
    if not parts:
        return ""
    return (" ".join(parts) +
            " Return a corrected answer in the same format that uses every "
            "input label exactly once.")

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
        "coverage_before_repair": len(seen) / len(all_ids) if all_ids else 0.0,
    }

def run_with_repair(ask, all_ids, max_retries=2):
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

        report = validate(groups, all_ids)
        attempts.append({"attempt": attempt, "error": error, **{
            k: report[k] for k in
            ("n_returned", "n_distinct", "n_expected", "valid")},
            "n_invalid": len(report["invalid"]),
            "n_duplicated": len(report["duplicated"]),
            "n_missing": len(report["missing"])})

        if error is None and report["valid"]:
            break
        feedback = repair_report_text(report)
        if not feedback and error is None:
            break                                     # nothing actionable

    final, actions = finalise(groups, all_ids)
    return final, {
        "calls": len(attempts),
        "attempts": attempts,
        "repaired": not attempts[-1]["valid"],
        **actions,
    }
```

**Please check:** the repair message contains only what the attacker could compute itself; the exhaustion order (discard invalid, first-occurrence-wins, then singletons) is the charge you want.

---

## C. Medoid-of-k selection (one-shot J only)

`harness/repair.py`

```python
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
```

**Please check:** no ground truth enters; agreement on the full directed-pair relation is the right selector.

---

## D. Spend cap

`harness/run_ledger.py`

```python
    def commit(self, usd):
        """Reserve projected spend at submission time."""
        self.data["spend"]["committed_usd"] += float(usd)
        self.save()

    def observe(self, usd):
        """Record actual spend once usage comes back."""
        self.data["spend"]["observed_usd"] += float(usd)
        self.save()

    def projected_total(self, next_usd=0.0):
        """The larger of committed and observed, plus what is about to be spent.

        Using the max rather than only one of them means an underestimating
        projection cannot hide real spend, and an overestimating one cannot be
        quietly forgiven by a cheaper outturn.
        """
        return max(self.committed, self.observed) + float(next_usd)

    def check_spend(self, next_usd):
        """Consulted BEFORE submitting. Returns (allowed, message)."""
        cap = self.data["max_spend_usd"]
        projected = self.projected_total(next_usd)
        if projected <= cap:
            return True, (f"projected ${projected:.2f} of ${cap:.2f} cap "
                          f"(committed ${self.committed:.2f}, "
                          f"observed ${self.observed:.2f})")

        lines = [
            f"REFUSED: this submission would bring projected spend to "
            f"${projected:.2f}, over the ${cap:.2f} cap.",
            f"  already committed ${self.committed:.2f}, "
            f"observed ${self.observed:.2f}, this step ${float(next_usd):.2f}",
            "",
            "  Documented cut order (RUN_PLAN), apply in this sequence:",
        ]
        running = projected
        for name, saving, why in CUT_ORDER:
            running -= saving
            lines.append(f"    drop {name:<28} -${saving:>6.2f} "
                         f"-> ${running:>7.2f}   {why}")
            if running <= cap:
                lines.append(f"    ^ this alone brings the run under the cap")
                break
        return False, "\n".join(lines)
```

**Please check:** max(committed, observed) is the right projection; checking before create() with commit immediately after is the correct ordering.

---

## Verification output (run from the project venv)

### G0 — metric identities

```
======================================================================
 G0 -- metric identities. Nothing downstream is trustworthy until
 these pass.
======================================================================

identity 1: perfect membership -> F1_J = (1+tau)/2, not tau
  [PASS] F1_J == (1+tau)/2 over 100 shuffles  -- max deviation 1.11e-16
  [PASS] full reversal -> F1_J 0.0 while tau = -1.0  -- F1_J=0.0000

identity 2: F1_J = F1_L * (C/K)
  [PASS] F1_J == F1_L * q on 4 constructed cases  -- max deviation 0.00e+00

identity 3: analytic baseline, joint == linkage / 2
  [PASS] baseline_joint * 2 == baseline_linkage  -- max deviation 0.00e+00
  [PASS] analytic baseline matches Monte-Carlo  -- max deviation 0.0029

behaviour on constructed answers (3 docs x 25 fragments)
  [PASS] perfect -> 1.000
  [PASS] one adjacent swap per document -> ~0.997, degrades gracefully  -- F1_J=0.9967
  [PASS] one bucket in TRUE order beats the arbitrary-order baseline  -- 0.4898 vs baseline 0.2449
  [PASS] advantage() is 0 at the baseline and 1 at perfect

K = 0 policy: undefined, never 0
  [PASS] K == 0 -> q is None, not 0.0  -- K=0 q=None
  [PASS] K == 0 -> a_order is None, not -1.0
  [PASS] micro_q over only-failed pools -> None, no ZeroDivisionError  -- q=None undefined=3
  [PASS] micro_q mixes defined and undefined pools correctly  -- q=1.0000 undefined=1

paired bootstrap: every cell resampled with the SAME indices
  [PASS] indices identical across 3 strategies x 2 attackers, 50 replicates
  [PASS] same seed reproduces the same index vectors

======================================================================
 G0 PASSED
======================================================================
```

### G1a — repair, medoid, ledger

```
======================================================================
 G1a -- repair protocol, medoid selection, spend ledger
======================================================================

validator: a deterministic function of the attacker's own view
  [PASS] missing detected  -- ['d', 'e']
  [PASS] duplicate detected
  [PASS] invented label detected
  [PASS] a clean answer validates
  [PASS] repair message carries bookkeeping only, no ground truth  -- These input labels are absent from your answer: b, c, d, e. ...

exhaustion: discard invalid, first occurrence wins, then singletons
  [PASS] every id present exactly once  -- ['a', 'b', 'c', 'd', 'e']
  [PASS] invalid discarded
  [PASS] duplicate dropped, first occurrence kept
  [PASS] unplaced ids became singletons
  [PASS] coverage before repair reported  -- 0.60
  [PASS] omitting a fragment lowers the score rather than hiding  -- 0.6667 < 1.0000

repair loop: retries are bounded and counted as attack cost
  [PASS] second attempt accepted
  [PASS] corrected answer is a valid partition
  [PASS] budget is bounded  -- calls=3
  [PASS] exhaustion still yields a full partition
  [PASS] repair recorded, not silent
  [PASS] a raising attacker consumes budget and still returns a partition
  [PASS] the error is recorded

medoid-of-k: truth-free, and repair must precede it
  [PASS] the answer agreeing with the others is chosen  -- idx=0 scores=[0.5, 0.5, 0.0]
  [PASS] identical inputs give a deterministic index
  [PASS] sparse answers win on agreement BEFORE repair (the trap)  -- idx=0
  [PASS] still resolvable after repair, and every candidate is complete  -- idx=0
  [PASS] agreement uses no ground truth (identical answers -> 1.0)

ledger: durable state and the spend cap
  [PASS] unknown step is pending
  [PASS] batch id persisted immediately
  [PASS] survives a process restart
  [PASS] completed steps are skippable
  [PASS] a submission under the cap is allowed  -- projected $50.00 of $100.00 cap
  [PASS] a submission over the cap is refused
  [PASS] refusal prints the documented cut order
  [PASS] projection uses max(committed, observed), not just one  -- committed 20, observed 45 -> 45.00

======================================================================
 G1a PASSED
======================================================================
```

---

## Known gaps, stated so they are not mistaken for oversights

- The hierarchical adversary, the blocker, and everything downstream are
  unwritten. The sparse-`M` clusterer and sparse rank aggregation you
  flagged as the remaining risks are Phase 2 and are not in this packet.
- `results/harness_results.json` still carries pre-rename `l_floor` keys;
  regenerating needs the ~15-minute prose Memon pass and is queued before
  the run.
- The cost model has not been regenerated against the real attack budget
  (medoid k, retry cap, deduplicated candidate edges), so every dollar
  figure in the plan is still stale.
