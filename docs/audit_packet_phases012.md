# Audit packet - Phases 0, 1 and 2 (complete)

**Actual committed code**, extracted from source by AST, not transcribed.
Head `8bdbddf`. Everything here is offline - no API calls, no spend.

Rounds R3-R6 are already incorporated: `(1+tau)/2` not tau; `F1_J = F1_L * (C/K)`;
analytic baseline; K=0 undefined; paired-bootstrap index sharing; floor to baseline;
medoid-k scoped to one-shot J; explicit-label repair; one query per unordered pair;
degree-normalised init rather than Bradley-Terry; exactly-N clustering; no
zero-filling of unobserved pairs.

---

## A. Ordered-pair F1, analytic baseline, decomposition

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

**Please check:** the three identities hold as implemented; `advantage` is per pool, never on grand means; `micro_q` returning None on sum(K)=0 is what you intended for a bootstrap replicate.

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

**Please check:** no ground truth enters; agreement on the full directed-pair relation is the right selector; scoping it away from the hierarchical pipeline is correct.

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

**Please check:** max(committed, observed) is the right projection; checking before create() and committing immediately after is the correct ordering.

---

## E. Sparse rank aggregation - THE HIGHEST-RISK COMPONENT

`harness/order_from_sim.py`

```python
def _canon(edges):
    """Normalise an edge dict to one antisymmetric entry per unordered pair.

    Accepts {(i, j): w} meaning "evidence that i precedes j". If both (i,j) and
    (j,i) are supplied they must agree in antisymmetry; the caller is expected to
    have derived one from the other, so disagreement is a bug worth surfacing.
    """
    out = {}
    for (i, j), w in edges.items():
        if i == j:
            raise ValueError(f"self-comparison for {i!r}")
        key = (i, j) if i <= j else (j, i)
        val = float(w) if i <= j else -float(w)
        if key in out and abs(out[key] - val) > 1e-9:
            raise ValueError(
                f"inconsistent evidence for {key}: {out[key]:+.4f} vs {val:+.4f}. "
                "Query each unordered pair once and derive the reverse."
            )
        out[key] = val
    return out
def net_win_scores(ids, edges):
    """Degree-normalised net-win per fragment.

    Raw sums favour whichever fragment happened to be compared more often, which
    is an artifact of candidate generation, not evidence about position.
    """
    canon = _canon(edges)
    total = defaultdict(float)
    degree = defaultdict(int)
    for (i, j), w in canon.items():
        total[i] += w
        total[j] -= w
        degree[i] += 1
        degree[j] += 1
    return {f: (total[f] / degree[f] if degree[f] else 0.0) for f in ids}
def objective(order, edges):
    """Agreement with observed evidence for a given ordering."""
    canon = _canon(edges)
    pos = {f: k for k, f in enumerate(order)}
    total = 0.0
    for (i, j), w in canon.items():
        if i not in pos or j not in pos:
            continue
        total += w if pos[i] < pos[j] else -w
    return total
def components(ids, edges):
    """Connected components of the OBSERVED-edge graph, deterministically ordered.

    Two fragments in different components have no evidence connecting them, at
    any remove. Components come back sorted by their smallest member so the
    caller's output does not depend on dict iteration order.
    """
    canon = _canon(edges)
    parent = {f: f for f in ids}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for (i, j) in canon:
        if i in parent and j in parent:
            ri, rj = find(i), find(j)
            if ri != rj:
                parent[ri] = rj

    groups = defaultdict(list)
    for f in ids:
        groups[find(f)].append(f)
    return sorted((sorted(v) for v in groups.values()), key=lambda g: g[0])
def _local_search(order, canon, max_passes=64):
    """Hill climbing against the exact objective: adjacent swaps, then insertions.

    Adjacent swap: neighbours a,b swap when w_ab < 0, i.e. the evidence says b
    precedes a. Cheap, and enough for locally-wrong pairs.

    Insertion: lift one fragment and reinsert it at the best position. This is
    what escapes a flat seed. Net-win gives every interior fragment of a chain a
    score of zero -- one win, one loss -- so the seed is arbitrary there and
    adjacent swaps alone converge short of the truth.

    Deterministic: candidate moves are scanned in index order and only a strict
    improvement is taken, so equal-scoring alternatives never flip the result.
    Still a local optimum, not a global one. Exact optimisation here is Kemeny
    and NP-hard; we do not need exact, we need honest.
    """
    order = list(order)
    n = len(order)
    swaps = 0

    for _ in range(max_passes):
        moved = False

        for p in range(n - 1):
            a, b = order[p], order[p + 1]
            key = (a, b) if a <= b else (b, a)
            w = canon.get(key)
            if w is None:
                continue
            w_ab = w if a <= b else -w          # evidence that a precedes b
            if w_ab < 0:
                order[p], order[p + 1] = b, a
                moved = True
                swaps += 1

        best = _objective_of(order, canon)
        for src in range(n):
            frag = order[src]
            rest = order[:src] + order[src + 1:]
            for dst in range(n):
                if dst == src:
                    continue
                cand = rest[:dst] + [frag] + rest[dst:]
                val = _objective_of(cand, canon)
                if val > best + 1e-12:          # strict, so ties never move
                    order, best = cand, val
                    moved = True
                    swaps += 1
                    break
            else:
                continue
            break

        if not moved:
            break
    return order, swaps
def order_cluster(ids, edges, max_passes=64):
    """Total order over `ids` from sparse directional evidence.

    Returns (order, info). `order` contains every id exactly once, always.
    `info` records how much of that order rests on evidence:

        n_components        1 means fully connected; >1 means the inter-component
                            order is ARBITRARY and carries no evidence
        arbitrary_pairs     count of pairs whose relative order was decided by
                            the tie rule rather than by evidence
        observed_pairs      pairs that actually received a score
        possible_pairs      m(m-1)/2
        objective           agreement achieved
        objective_max       sum |w| -- the value if every observed pair were
                            satisfied; unreachable when evidence has cycles
        swaps               local-search moves

    The tie rule between components is deliberately EVIDENCE-FREE: components
    are concatenated in order of their smallest member. Ordering them by, say,
    mean score would dress an arbitrary decision as a measured one. Arbitrary is
    fine; arbitrary and labelled is honest.
    """
    ids = list(ids)
    m = len(ids)
    if m <= 1:
        return list(ids), {
            "n_components": 1 if m else 0, "arbitrary_pairs": 0,
            "observed_pairs": 0, "possible_pairs": 0,
            "objective": 0.0, "objective_max": 0.0, "swaps": 0,
            "fully_connected": True,
        }

    idset = set(ids)
    canon = {k: v for k, v in _canon(edges).items()
             if k[0] in idset and k[1] in idset}

    comps = components(ids, canon)
    scores = net_win_scores(ids, canon)

    order = []
    swaps = 0
    for comp in comps:
        # descending net-win: earlier fragments should win more comparisons
        seeded = sorted(comp, key=lambda f: (-scores[f], f))
        improved, n = _local_search(seeded, canon, max_passes)
        order.extend(improved)
        swaps += n

    # pairs whose relative order no evidence path could have determined
    sizes = [len(c) for c in comps]
    arbitrary = sum(a * b for i, a in enumerate(sizes) for b in sizes[i + 1:])

    return order, {
        "n_components": len(comps),
        "component_sizes": sizes,
        "arbitrary_pairs": arbitrary,
        "observed_pairs": len(canon),
        "possible_pairs": m * (m - 1) // 2,
        "objective": objective(order, canon),
        "objective_max": sum(abs(w) for w in canon.values()),
        "swaps": swaps,
        "fully_connected": len(comps) == 1,
    }
```

**Please check:** degree normalisation is the right debiasing; adjacent-swap PLUS insertion is an adequate neighbourhood (adjacent-only failed a reversed chain at objective 2 of 4); the evidence-free inter-component tie rule with arbitrary_pairs reported is honest; rejecting Bradley-Terry on connectivity grounds was right.

---

## F. Sparse clustering - absence is absence

`harness/sparse_cluster.py`

```python
def connected_components(ids, edges):
    """Components of the observed-edge graph, deterministically ordered.

    edges: {(i, j): score} for observed pairs only. Any score present counts as
    a link for connectivity purposes -- connectivity asks whether we have ANY
    evidence relating two fragments, not whether that evidence was positive.
    """
    parent = {f: f for f in ids}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for (i, j) in edges:
        if i in parent and j in parent:
            ri, rj = find(i), find(j)
            if ri != rj:
                parent[ri] = rj

    groups = defaultdict(list)
    for f in ids:
        groups[find(f)].append(f)
    return sorted((sorted(v) for v in groups.values()), key=lambda g: g[0])
def bridge_candidates(components_list, k_per_pair=1):
    """Pairs to score next so that too-fragmented evidence can reach N groups.

    Returns cross-component pairs, nearest-first by component index so the
    smallest number of new queries connects the most. Deterministic: the caller
    spends real money on these, so the same graph must always ask the same
    questions.
    """
    out = []
    for a in range(len(components_list)):
        for b in range(a + 1, len(components_list)):
            ca, cb = components_list[a], components_list[b]
            for t in range(min(k_per_pair, len(ca), len(cb))):
                out.append((ca[t], cb[t]))
    return out
def cluster_known_n(ids, edges, n_clusters):
    """Merge by descending membership score, stop at exactly n_clusters.

    ids        : every fragment that must be placed
    edges      : {(i, j): M_ij} for OBSERVED pairs only, symmetric in meaning
    n_clusters : the oracle document count N

    Returns (clusters, info). `clusters` is a list of lists covering every id
    exactly once, and len(clusters) == n_clusters whenever that is achievable.

    info records what the result rests on:
        reached_n           did the merge actually land on N
        components_before   components of the observed graph before merging
        needs_bridges       True when the evidence graph is too fragmented to
                            reach N without new comparisons
        merges              merges performed
        forced_merges       merges that joined components with NO observed edge
                            between them -- zero for a graph-native result
        singletons          clusters of size 1 in the output

    When the graph has MORE than n_clusters components, N is not reachable
    without inventing links. Rather than fabricate them, this returns the
    components as-is with needs_bridges=True so the caller can spend budget on
    bridge comparisons and retry. Manufacturing merges from absent evidence is
    the failure this module exists to prevent.
    """
    ids = list(ids)
    if n_clusters < 1:
        raise ValueError("n_clusters must be >= 1")
    if len(ids) <= n_clusters:
        return [[f] for f in sorted(ids)], {
            "reached_n": len(ids) == n_clusters, "components_before": len(ids),
            "needs_bridges": False, "merges": 0, "forced_merges": 0,
            "singletons": len(ids),
        }

    idset = set(ids)
    obs = {(i, j): float(w) for (i, j), w in edges.items()
           if i in idset and j in idset and i != j}

    comps = connected_components(ids, obs)
    if len(comps) > n_clusters:
        # Too fragmented. Do NOT invent links to force N.
        return comps, {
            "reached_n": False, "components_before": len(comps),
            "needs_bridges": True, "merges": 0, "forced_merges": 0,
            "singletons": sum(1 for c in comps if len(c) == 1),
        }

    parent = {f: f for f in ids}
    size = {f: 1 for f in ids}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    # Descending score; ties broken on the pair itself so the merge order is
    # reproducible rather than dependent on dict insertion order.
    ranked = sorted(obs.items(), key=lambda kv: (-kv[1], kv[0]))

    n_live = len(ids)
    merges = 0
    for (i, j), _w in ranked:
        if n_live <= n_clusters:
            break
        ri, rj = find(i), find(j)
        if ri == rj:
            continue
        if size[ri] < size[rj] or (size[ri] == size[rj] and ri > rj):
            ri, rj = rj, ri
        parent[rj] = ri
        size[ri] += size[rj]
        n_live -= 1
        merges += 1

    groups = defaultdict(list)
    for f in ids:
        groups[find(f)].append(f)
    clusters = sorted((sorted(v) for v in groups.values()), key=lambda g: g[0])

    return clusters, {
        "reached_n": len(clusters) == n_clusters,
        "components_before": len(comps),
        "needs_bridges": False,
        "merges": merges,
        "forced_merges": 0,          # graph-native: never merges without an edge
        "singletons": sum(1 for c in clusters if len(c) == 1),
    }
```

**Please check:** REFUSING to reach N when the observed graph has more than N components - returning needs_bridges rather than inventing links - is the correct call; exactly-N as a merge stopping condition genuinely avoids the fcluster maxclust shortfall; descending-score merge order with deterministic tie-breaking is defensible as sparse single-linkage.

---

## G. Two-channel derivation and orientation randomisation

`adversaries/hierarchical.py`

```python
def pair_prompt(shown):
    """One prompt covering many pairs. `shown` is [(idx, a_text, b_text), ...].

    Deliberately asks for ONE precedence number, not two. The reverse is
    derived.
    """
    blocks = []
    for idx, a_text, b_text in shown:
        blocks.append(f"{idx}.\n  A: {a_text}\n  B: {b_text}")
    return (
        "Each numbered item below is a PAIR of text fragments taken from a "
        "collection of documents that were split up and mixed together.\n\n"
        "For each pair, judge two things independently:\n"
        "  same   — the probability the two fragments came from the SAME "
        "document, from 0.0 to 1.0\n"
        "  before — ASSUMING they are from the same document, the probability "
        "that A appeared BEFORE B in it, from 0.0 to 1.0\n\n"
        + "\n\n".join(blocks) +
        f"\n\nReturn ONLY a JSON array of {len(shown)} objects in the same "
        'order, each {"same": <number>, "before": <number>}. '
        "No explanation, no markdown."
    )
def orient(pairs, seed):
    """Decide, per pair, which fragment is shown as A. Deterministic from seed.

    Returns [(i, j, flipped)] where flipped=True means j was shown first, so a
    returned `before` probability refers to j preceding i and must be inverted
    when deriving W_ij.
    """
    rng = random.Random(seed)
    return [(i, j, rng.random() < 0.5) for (i, j) in pairs]
def derive(i, j, flipped, same, before):
    """Turn one raw answer into symmetric M and antisymmetric W for (i, j).

    `before` is P(shown-first precedes shown-second). When the pair was flipped
    that is P(j precedes i), so P(i precedes j) = 1 - before.
    """
    p_ij = (1.0 - before) if flipped else before
    return {"M": float(same), "W": 2.0 * float(p_ij) - 1.0, "p_ij": p_ij}
```

**Please check:** one query per unordered pair with the reverse derived is right; the flip inversion p_ij = 1 - before is correct; randomised orientation from a stored seed addresses the positional-bias concern.

---

## H. The pipeline

`adversaries/hierarchical.py`

```python
def top_k_candidates(frag_ids, text_by_id, k=DEFAULT_K):
    """Each fragment's k most similar neighbours, as UNDIRECTED pairs.

    Union-kNN: an edge exists when EITHER endpoint selects the other. Reciprocal
    choices collapse to one pair, so the edge count is well below n*k — which is
    why the cost model must count deduplicated edges rather than n*k.

    Dense O(n^2) on purpose. Within a pool that is ~178 fragments, about 15k
    comparisons, trivial. Exact top-k from a pairwise similarity CLOSURE is
    O(n^2) regardless of how few results are kept, so pretending otherwise at
    this scale would buy nothing. Full-corpus blocking (16,524 fragments, ~136M
    pairs) is a different problem and needs an inverted index over TF-IDF terms;
    that is Phase 3, not this function.
    """
    sim = build_tfidf(frag_ids, text_by_id)
    n = len(frag_ids)
    comparisons = 0
    pairs = set()
    for i, a in enumerate(frag_ids):
        scored = []
        for j, b in enumerate(frag_ids):
            if i == j:
                continue
            scored.append((sim(a, b), b))
            comparisons += 1
        scored.sort(key=lambda t: (-t[0], t[1]))
        for _s, b in scored[:k]:
            pairs.add((a, b) if a <= b else (b, a))
    return sorted(pairs), {
        "n_fragments": n,
        "k": k,
        "comparisons": comparisons,
        "possible_pairs": n * (n - 1) // 2,
        "candidate_pairs": len(pairs),
        "reduction_ratio": (1 - len(pairs) / (n * (n - 1) / 2)) if n > 1 else 0.0,
    }
def attack(fragments, n_records, score_fn, k=DEFAULT_K, seed=42,
           max_bridge_rounds=MAX_BRIDGE_ROUNDS):
    """Full hierarchical attack over one pool.

    fragments  : [{"fragment_id": ..., "text": ...}] — ALREADY MASKED
    n_records  : oracle document count (known-N, the primary condition)
    score_fn   : pairs -> (m_edges, w_edges, rows). Injected so the LLM scorer,
                 a statistical scorer, or a test oracle all drive the same
                 pipeline.

    Returns (groups, telemetry). `groups` is a list of ordered lists covering
    every fragment exactly once — the same shape one-shot J emits.
    """
    frag_ids = [f["fragment_id"] for f in fragments]
    text_by_id = {f["fragment_id"]: f["text"] for f in fragments}

    pairs, cand_info = top_k_candidates(frag_ids, text_by_id, k=k)
    m_edges, w_edges, rows = score_fn(pairs)

    # Clustering may report that the observed graph is too fragmented to reach
    # N. Rather than invent links, ask for bridge comparisons and retry.
    bridge_rounds = 0
    bridge_pairs_scored = 0
    clusters, cinfo = cluster_known_n(frag_ids, m_edges, n_records)
    while cinfo["needs_bridges"] and bridge_rounds < max_bridge_rounds:
        comps = connected_components(frag_ids, m_edges)
        new_pairs = [p for p in bridge_candidates(comps) if p not in m_edges]
        if not new_pairs:
            break
        bm, bw, brows = score_fn(new_pairs)
        m_edges.update(bm)
        w_edges.update(bw)
        rows.extend(brows)
        bridge_pairs_scored += len(brows)
        bridge_rounds += 1
        clusters, cinfo = cluster_known_n(frag_ids, m_edges, n_records)

    groups, order_info = [], []
    for cl in clusters:
        inner = {kk: v for kk, v in w_edges.items()
                 if kk[0] in set(cl) and kk[1] in set(cl)}
        ordered, oinfo = order_cluster(cl, inner)
        groups.append(ordered)
        order_info.append(oinfo)

    placed = [x for g in groups for x in g]
    telemetry = {
        "candidates": cand_info,
        "clustering": cinfo,
        "bridge_rounds": bridge_rounds,
        "bridge_pairs_scored": bridge_pairs_scored,
        "n_clusters": len(groups),
        "n_records_asked": n_records,
        "exact_n": len(groups) == n_records,
        "coverage": len(set(placed)) / len(frag_ids) if frag_ids else 0.0,
        "clusters_disconnected": sum(1 for o in order_info
                                     if not o["fully_connected"]),
        "arbitrary_pairs_total": sum(o["arbitrary_pairs"] for o in order_info),
        "observed_pairs_total": sum(o["observed_pairs"] for o in order_info),
        "order_info": order_info,
        "scored_edges": len(m_edges),
    }
    return groups, telemetry
```

**Please check:** the bridge-repair loop terminates and cannot invent evidence; injecting the scorer keeps LLM / statistical / test attackers on one code path; the telemetry captures what a reviewer would need.

---

## Verification output (project venv)

### G0 - metric identities

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

### G1a - repair, medoid, ledger

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

### Phase 2 core - sparse ordering and clustering

```
======================================================================
 Phase 2 core -- sparse ordering and sparse clustering
======================================================================

ordering: recovers the truth from consistent evidence
  [PASS] a consistent chain is recovered exactly  -- ['a', 'b', 'c', 'd', 'e']
  [PASS] every id appears exactly once
  [PASS] reported as fully connected
  [PASS] no arbitrary pairs when connected
  [PASS] input order does not affect the result  -- ['a', 'b', 'c', 'd', 'e']
  [PASS] reversed evidence gives the reversed order  -- ['e', 'd', 'c', 'b', 'a']

ordering: degree normalisation, the bias the reviewer flagged
  [PASS] scores are per-comparison, not sums  -- a=0.200 (2 comparisons)  b=0.900 (1)
  [PASS] raw sums would have ranked them the other way  -- raw a=0.40 vs b=0.90 -- normalised keeps b ahead

ordering: disconnected clusters are labelled, not laundered
  [PASS] still a total order over every id  -- ['a', 'b', 'c', 'd']
  [PASS] disconnection is reported  -- components=2
  [PASS] arbitrary pairs counted (2 x 2 across the split)  -- 4
  [PASS] within-component evidence still honoured
  [PASS] components are deterministic and sorted  -- [['a', 'b'], ['c', 'd']]

ordering: cycles and missing evidence still yield a complete order
  [PASS] a cyclic tournament still returns every id once  -- ['a', 'b', 'c']
  [PASS] objective cannot reach its maximum under a cycle  -- 1.00 < 3.00
  [PASS] 8 fragments, 3 observed pairs -> complete order
  [PASS] sparsity is visible in the record  -- 3/28 pairs observed
  [PASS] local search improves or holds the objective

ordering: contradictory both-direction evidence is a bug, not a vote
  [PASS] inconsistent pair raises rather than averaging  -- inconsistent evidence for ('a', 'b'): +0.8000 vs -0.6000. Qu...
  [PASS] algebraically consistent reverse is accepted

clustering: exactly N, by construction
  [PASS] returns exactly N clusters  -- 3
  [PASS] every fragment placed exactly once
  [PASS] the true triples are recovered  -- [['f0', 'f1', 'f2'], ['f3', 'f4', 'f5'], ['f6', 'f7', 'f8']]
  [PASS] no merge was forced without an edge
  [PASS] exactly N holds at N = 1, 2, 4, 5

clustering: absence is absence, never a confident negative
  [PASS] refuses to invent a link, reports needs_bridges  -- components=3 asked=2
  [PASS] returns the honest components rather than a fabricated N  -- 3
  [PASS] nothing lost while refusing
  [PASS] bridge pairs proposed across components  -- [('f0', 'f2'), ('f0', 'f4'), ('f2', 'f4')]
  [PASS] bridge pairs are cross-component, never within
  [PASS] after one bridge, N becomes reachable  -- components_before=2

clustering: tie-heavy input is deterministic (the maxclust trap)
  [PASS] 20 runs on all-ties give identical, exactly-3 output  -- no silent shortfall, unlike fcluster maxclust

======================================================================
 PHASE 2 CORE PASSED
======================================================================
```

### Hierarchical attacker - end to end

```
======================================================================
 Hierarchical attacker -- end to end, offline, no spend
======================================================================

derivation: one query per pair, both directions derived
  [PASS] unflipped: W = 2p - 1  -- W=0.60
  [PASS] flipped: the answer refers to b preceding a, so W inverts  -- W=-0.60
  [PASS] total uncertainty gives W = 0
  [PASS] orientation is randomised, not fixed  -- 52% flipped
  [PASS] orientation is reproducible from the seed

candidate generation: union-kNN, deduplicated
  [PASS] edges are undirected and deduplicated
  [PASS] count is well below n*k -- reciprocal choices collapse  -- 60 pairs vs n*k = 120
  [PASS] reduction ratio reported  -- 78.3% of all pairs skipped
  [PASS] candidates are enriched for true co-members  -- 60/60 = 100% same-document

pipeline: perfect evidence -> near-perfect reconstruction
  [PASS] every fragment placed exactly once  -- 24 placed
  [PASS] exactly N clusters  -- 4 clusters
  [PASS] reconstruction far above the analytic baseline  -- F1_J=1.0000 vs baseline 0.1786
        F1_J 1.0000   baseline 0.1786   pairs scored 78

pipeline: a coin-flip oracle must collapse toward the baseline
        oracle 100% -> F1_J 1.0000
        oracle 75% -> F1_J 0.2667
        oracle 50% -> F1_J 0.1926
  [PASS] perfect evidence beats noisy evidence  -- 1.000 > 0.267
  [PASS] noisy beats coin-flip  -- 0.267 > 0.193
  [PASS] a coin-flip oracle does NOT beat the baseline by much  -- 0.193 vs baseline 0.179

output contract: identical shape to one-shot J, same scorer
  [PASS] a list of lists of fragment ids
  [PASS] the shared scorer accepts it with no special-casing  -- F1_J=0.7213  q=0.8462
  [PASS] telemetry records what the order rests on  -- disconnected clusters 0, arbitrary pairs 0

bridge repair: too-sparse evidence asks for more, never invents
  [PASS] still covers every fragment under a starved k
  [PASS] bridge rounds recorded  -- rounds=1 extra pairs=15
  [PASS] no cluster was merged without an observed edge

======================================================================
 HIERARCHICAL ATTACKER PASSED
======================================================================
```

---

## Three findings I want challenged, not merely checked

**1. The attacker is brittle to membership error, and the fall is a cliff.**
With a synthetic oracle whose accuracy is a dial:

```
oracle 100%  ->  F1_J 1.0000     (analytic baseline 0.1786)
oracle  75%  ->  F1_J 0.2667
oracle  50%  ->  F1_J 0.1926     a coin flip lands AT the baseline
```

The coin-flip row is reassuring - an attacker scoring well there would be reading
something other than its evidence. The 100-to-75 cliff is not. Single-linkage
merging propagates membership errors: one wrong high-confidence edge welds two
documents and the damage cascades.

**Is single-linkage the wrong merge rule, given we deliberately refuse to impute
missing pairs?** Average-linkage needs a declared rule for how an unobserved pair
enters a cluster-to-cluster average - which is exactly the imputation we banned -
so I kept single-linkage. I am not confident that is the right trade.

**2. Candidate generation on synthetic data was too easy.** 100% of retained
candidates were true co-members, because the synthetic pool gives each document a
distinct topic vocabulary. Real PMC case reports are all clinical prose with heavy
shared terminology. That enrichment figure should be treated as meaningless until
measured on the real corpus, and I would rather say so than let it read as
validation.

**3. Local search is a local optimum and I have not bounded the gap.** Adjacent
swaps plus insertion recovered the optimum on every constructed case, and on a
12-fragment graph with 27 of 66 pairs observed and 15% label noise it reached
objective 27.0 of 27.0 - perfectly satisfying evidence that was itself wrong in 11
places. But there is no bound on how far from Kemeny-optimal it can sit on
adversarial input. Does that need one, or is 'optimises a stated objective,
locally' sufficient for this venue?

---

## Known gaps, stated so they are not read as oversights

- **Phase 3 (blocker) not built.** `top_k_candidates` is dense O(n^2) - correct
  within a pool, useless at 16,524 fragments. The inverted index and its
  instrumentation are unwritten.
- **Memon joint adaptation not built.** Grouping and ordering remain separate code
  paths; the plan is B_stat for grouping, `memon.py::score_pair` for ordering.
- **Cost model still stale.** Not regenerated against medoid k, the retry budget, or
  deduplicated pair-scoring volume. Every dollar figure in the plan is unreliable.
- **`results/harness_results.json`** still carries pre-rename `l_floor` keys; needs
  the ~15-minute prose Memon pass.
- **No LLM has driven this pipeline.** `score_pairs_llm` is written and preflighted
  but has never been called against a real model.
