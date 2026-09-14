"""
visible_metrics.py — duplicate-invariant VISIBLE-TEXT reconstruction metrics for
the POST-HOC EXPLORATORY — CONTROLLED SINGLE-TOKEN EDGE-CASE EXPERIMENT.
FROZEN (RUN_DECISIONS D16; docs/single_token_edge_design.md). Validated on
constructed data only (harness/test_visible_metrics.py); not yet applied to any
experimental attacker output.

Why: the ordinary game-J scorer tracks hidden fragment ids. At single-token
granularity many fragments share visible text ("the", "the", ...), and swapping
the hidden ids of two identical visible tokens is invisible to any attacker yet
penalised by an id-level scorer. These metrics score only what is observable:
the visible whitespace-token sequences.

Both representations are converted to whitespace tokens before scoring, so a
sentence reconstruction and a token reconstruction of the same text share one
scale and a perfect reconstruction scores 1 in both.

  V_L  max over one-to-one assignments (predicted group -> true document) of the
       summed multiset intersection of visible tokens, / total true tokens
  V_J  the same with token-level LCS length in place of multiset overlap
  q_V  V_J / V_L, a diagnostic only
V_J <= V_L always: for any pairing LCS <= multiset overlap, so the LCS-optimal
assignment's total is <= its own overlap total <= the overlap maximum.

Hungarian assignment: scipy.optimize.linear_sum_assignment (maximize), which is
deterministic for a given matrix. The reported V_L / V_J are the optimal VALUES,
which do not depend on how ties between equally good assignments are broken.

Nulls (the analytic b_J does not apply to visible metrics):
  oracle-size permutation null (PRIMARY): permute all fragment labels, cut into 7
      groups with the TRUE per-document fragment counts, permuted order within.
  predicted-structure permutation null (ROBUSTNESS): permute labels into the
      attacker's own predicted group sizes / output positions.
Advantage: A_V = (V - mean(null V)) / (1 - mean(null V)): the fraction of the gap
between the pool-specific null mean and perfect visible reconstruction achieved.
"""

import hashlib

import numpy as np
from scipy.optimize import linear_sum_assignment

NAMESPACE = "single-token-edge-v1"


def tokens(text):
    return text.split()


def masks_of(b):
    """Per-symbol bit masks over the positions of sequence b."""
    m = {}
    for j, t in enumerate(b):
        m[t] = m.get(t, 0) | (1 << j)
    return m


def lcs_len(a, b_masks, m):
    """Bit-parallel LCS length (Crochemore et al. 2001; Hyyro 2004): the LCS of
    integer sequence `a` and a length-m sequence whose symbol masks are b_masks.
    V starts all ones; each symbol of a does V = (V + U) | (V - U) with
    U = V & mask; the LCS length is the number of zero bits of V."""
    if m == 0 or not a:
        return 0
    full = (1 << m) - 1
    v = full
    for t in a:
        mk = b_masks.get(t)
        if mk:
            u = v & mk
            v = ((v + u) | (v - u)) & full
    return m - v.bit_count()


def lcs_dp(a, b):
    """Reference O(n m) dynamic programme, for tests."""
    prev = [0] * (len(b) + 1)
    for x in a:
        cur = [0]
        for j, y in enumerate(b):
            cur.append(prev[j] + 1 if x == y else max(prev[j + 1], cur[j]))
        prev = cur
    return prev[-1]


class PoolScorer:
    """Visible-text scorer for one pool. truth_order: {doc_id: [fragment ids in
    true order]}; text_of: {fragment id: visible text shown to the attacker}."""

    def __init__(self, truth_order, text_of):
        self.docs = sorted(truth_order)
        vocab = {}
        self.frag_seq = {f: [vocab.setdefault(t, len(vocab)) for t in tokens(text_of[f])]
                         for d in self.docs for f in truth_order[d]}
        self.true_seq = [[t for f in truth_order[d] for t in self.frag_seq[f]] for d in self.docs]
        self.total = sum(len(s) for s in self.true_seq)
        self.nv = len(vocab)
        self.true_counts = np.stack([np.bincount(s, minlength=self.nv) for s in self.true_seq])
        self.true_masks = [masks_of(s) for s in self.true_seq]
        self.true_len = [len(s) for s in self.true_seq]
        self.all_ids = sorted(self.frag_seq)
        self.sizes = [len(truth_order[d]) for d in self.docs]

    def _clean(self, groups):
        """Unknown ids dropped; an id repeated anywhere counts once (first
        occurrence); fragments placed nowhere become singleton groups -- the
        game-J scorer's reading of a dropped fragment."""
        seen, out = set(), []
        for g in groups:
            h = []
            for f in g:
                if f in self.frag_seq and f not in seen:
                    seen.add(f)
                    h.append(f)
            out.append(h)
        out += [[f] for f in self.all_ids if f not in seen]
        return out

    def score_sequences(self, seqs):
        T = len(self.true_seq)
        rows = max(len(seqs), T)                          # empty groups pad to a square problem
        lm = np.zeros((rows, T))
        jm = np.zeros((rows, T))
        for i, s in enumerate(seqs):
            if not s:
                continue
            c = np.bincount(s, minlength=self.nv)
            lm[i] = np.minimum(c[None, :], self.true_counts).sum(1)
            for j in range(T):
                if lm[i, j] > 0:
                    jm[i, j] = lcs_len(s, self.true_masks[j], self.true_len[j])
        r, c = linear_sum_assignment(lm, maximize=True)
        r2, c2 = linear_sum_assignment(jm, maximize=True)
        vl = float(lm[r, c].sum()) / self.total
        vj = float(jm[r2, c2].sum()) / self.total
        return {"V_L": vl, "V_J": vj, "q_V": (vj / vl) if vl else None,
                "assign_L": [(int(a), self.docs[b]) for a, b in zip(r, c) if lm[a, b] > 0],
                "assign_J": [(int(a), self.docs[b]) for a, b in zip(r2, c2) if jm[a, b] > 0]}

    def score(self, groups):
        """groups: the attacker's predicted groups, each an ordered list of fragment ids."""
        cleaned = self._clean(groups)
        return self.score_sequences([[t for f in g for t in self.frag_seq[f]] for g in cleaned])

    def structure_of(self, groups):
        """The predicted group sizes after the same cleaning -- the positions the
        predicted-structure null fills."""
        return [len(g) for g in self._clean(groups) if g]


def null_rng(pool_id, condition, kind, namespace=NAMESPACE):
    h = hashlib.sha256(f"{namespace}|{pool_id}|{condition}|{kind}".encode("utf-8")).hexdigest()
    return np.random.default_rng(int(h[:16], 16))


def _perm_null(ps, sizes, n_perm, rng):
    ids = ps.all_ids
    cuts = np.cumsum(sizes)[:-1]
    out = np.empty((n_perm, 2))
    for k in range(n_perm):
        perm = [ids[i] for i in rng.permutation(len(ids))]
        groups = np.split(np.arange(len(perm)), cuts)
        seqs = [[t for i in g for t in ps.frag_seq[perm[i]]] for g in groups]
        s = ps.score_sequences(seqs)
        out[k] = (s["V_L"], s["V_J"])
    return out


def oracle_size_null(ps, n_perm, rng):
    """PRIMARY null: labels permuted into the TRUE per-document fragment counts."""
    return _perm_null(ps, ps.sizes, n_perm, rng)


def predicted_structure_null(ps, groups, n_perm, rng):
    """ROBUSTNESS null: labels permuted into the attacker's own predicted structure."""
    return _perm_null(ps, ps.structure_of(groups), n_perm, rng)


def advantage(v, null_mean):
    return (v - null_mean) / (1.0 - null_mean) if null_mean < 1 else None
