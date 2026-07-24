"""
Memon-style n-gram baseline for fragment reassembly.

Paper method (section: "n-order context model"):
  1. Build a character n-gram model by accumulating counts from ALL fragment texts.
  2. Score ordered pair (A, B): place a sliding window of size n at the end of A,
     slide one position at a time into B, and at each step estimate P(next char)
     using the shared model. Accumulate log P over d steps (d <= n per paper).
  3. Game O: score all permutations; pick the one maximising total boundary log P.
  4. Game L: build pairwise affinity matrix from pair scores; cluster with
     agglomerative clustering into n_records groups.

Data-type note:
  The model is trained on *individual* fragments, so it never observes cross-field
  boundary transitions (e.g. end-of-name -> start-of-SSN). Almost every boundary
  step therefore falls back to the smoothed prior, which makes pairs nearly
  indistinguishable. This is expected behaviour for short PII fields; the method
  is designed for longer natural-language fragments where within-fragment n-grams
  genuinely predict continuation. Results for Game O are below the NCD baseline
  for this reason; Game L is comparable. Both are documented in results output.

Parameters: n=2, d=2 (strict paper recommendation d <= n)
"""

import os
import json
import math
import numpy as np
from collections import defaultdict
from itertools import combinations, permutations
from scipy.cluster.hierarchy import linkage as hier_linkage, fcluster
from scipy.spatial.distance import squareform
from scipy.stats import kendalltau

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # repo root
FRAGMENTS_PATH  = os.path.join(_ROOT, "data", "identifier", "fragments.jsonl")
ANSWER_KEY_PATH = os.path.join(_ROOT, "data", "identifier", "answer_key.jsonl")
N = 2   # n-gram order
D = N   # boundary depth (d <= n as the paper specifies)


# ── loading ────────────────────────────────────────────────────────────────────

def load_jsonl(path):
    rows = []
    with open(path) as f:
        for line in f:
            s = line.strip()
            if s:
                rows.append(json.loads(s))
    return rows

def load_fragments(path):
    return load_jsonl(path)

def load_answer_key(path):
    rows = load_jsonl(path)
    by_record = {}
    for row in rows:
        by_record.setdefault(row["record_id"], []).append(row)
    return {
        rec_id: [r["fragment_id"] for r in sorted(frags, key=lambda r: r["position"])]
        for rec_id, frags in by_record.items()
    }

def group_by_record(fragments):
    groups = {}
    for f in fragments:
        groups.setdefault(f["record_id"], []).append(f["fragment_id"])
    return groups

def build_text_map(fragments):
    return {f["fragment_id"]: f["text"] for f in fragments}


# ── n-gram model ───────────────────────────────────────────────────────────────

def build_model(fragments, n):
    """
    Accumulate character n-gram counts from each fragment into one shared model.
    model[context][next_char] = count
    """
    model = defaultdict(lambda: defaultdict(int))
    for frag in fragments:
        text = frag["text"]
        for i in range(len(text) - n):
            model[text[i:i+n]][text[i+n]] += 1
    return model

def build_vocab(fragments):
    chars = set()
    for f in fragments:
        chars.update(f["text"])
    return chars

def p_char(model, context, char, vocab, alpha=0.5):
    """P(char | context) with Laplace smoothing over observed vocabulary."""
    ctx = model.get(context, {})
    denom = sum(ctx.values()) + alpha * len(vocab)
    return (ctx.get(char, 0) + alpha) / denom


# ── pair scoring ───────────────────────────────────────────────────────────────

def score_pair(text_a, text_b, model, vocab, n, d):
    """
    log P(B follows A) via the paper's sliding-window method.

    Window of size n starts at the end of A and slides into B one position at a
    time. At step i, context = last n chars of (A + B[:i]). We accumulate
    log P(B[i] | context) for i in 0 .. min(d, len(B)) - 1.

    With d <= n every context includes at least one character from A, so scores
    are genuinely boundary-sensitive. Setting d > n means later steps draw their
    context entirely from B (interior scoring), which dilutes the boundary signal.
    """
    if len(text_a) < n or not text_b:
        return -math.inf

    log_p = 0.0
    steps = min(d, len(text_b))
    for i in range(steps):
        context = (text_a + text_b[:i])[-n:]
        if len(context) < n:
            continue
        log_p += math.log(p_char(model, context, text_b[i], vocab))
    return log_p


# ── Game O: ordering ──────────────────────────────────────────────────────────

def memon_order_guess(frag_ids, text_map, model, vocab, n, d):
    """
    Exhaustive search over all 4! = 24 permutations.
    Permutation score = sum of score_pair for all adjacent (A, B) in the sequence.
    """
    best, best_score = None, -math.inf
    for perm in permutations(frag_ids):
        score = sum(
            score_pair(text_map[perm[i]], text_map[perm[i+1]], model, vocab, n, d)
            for i in range(len(perm) - 1)
        )
        if score > best_score:
            best_score, best = score, list(perm)
    return best


# ── Game L: linkage ───────────────────────────────────────────────────────────

def memon_linkage_guess(fragments, text_map, model, vocab, n, d, n_records):
    """
    Build a pairwise affinity matrix from directed pair scores (symmetrised as
    max of both directions), convert to distance, cluster with average-linkage
    agglomeration.
    """
    frag_ids = [f["fragment_id"] for f in fragments]
    N_f = len(frag_ids)

    print(f"  Scoring {N_f * (N_f-1):,} ordered pairs...")
    S = np.zeros((N_f, N_f))
    for i in range(N_f):
        for j in range(N_f):
            if i != j:
                S[i, j] = score_pair(
                    text_map[frag_ids[i]], text_map[frag_ids[j]],
                    model, vocab, n, d
                )

    A = np.maximum(S, S.T)
    span = A.max() - A.min()
    dist = 1.0 - ((A - A.min()) / span) if span > 0 else np.ones_like(A)
    np.fill_diagonal(dist, 0.0)

    Z = hier_linkage(squareform(dist), method="average")
    labels = fcluster(Z, t=n_records, criterion="maxclust")

    groups = {}
    for idx, label in enumerate(labels):
        groups.setdefault(int(label), []).append(frag_ids[idx])
    return groups


# ── scoring ───────────────────────────────────────────────────────────────────

def eval_ordering(guessed, true_order):
    true_rank = {fid: i for i, fid in enumerate(true_order)}
    return kendalltau(
        [true_rank[f] for f in guessed], list(range(len(true_order)))
    ).statistic

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


# ── main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    fragments  = load_fragments(FRAGMENTS_PATH)
    true_order = load_answer_key(ANSWER_KEY_PATH)
    text_map   = build_text_map(fragments)
    vocab      = build_vocab(fragments)

    print(f"Loaded {len(fragments)} fragments across {len(true_order)} records.")
    print(f"Vocab: {len(vocab)} chars | n={N} | d={D}\n")

    model = build_model(fragments, N)
    print(f"Built n-gram model: {len(model)} unique {N}-gram contexts, "
          f"{sum(sum(v.values()) for v in model.values())} total observations.\n")

    # ── Game O ──
    print("=== Game O: Ordering ===")
    grouped = group_by_record(fragments)
    taus = []
    for rec_id, frag_ids in grouped.items():
        guess = memon_order_guess(frag_ids, text_map, model, vocab, N, D)
        taus.append(eval_ordering(guess, true_order[rec_id]))
    avg_tau = sum(taus) / len(taus)

    print(f"  Memon n-gram (n={N}, d={D})   avg tau : {avg_tau:.4f}")
    print(f"  NCD baseline                  avg tau :  0.1400")
    print(f"  Random baseline               avg tau : ~0.0000")
    print()
    print("  Note: n-gram ordering underperforms NCD on this data because the")
    print("  model never observes cross-field boundary transitions during training")
    print("  (fragments are trained independently). With only ~465 bigram contexts")
    print("  from 200 short PII strings, almost every boundary step falls back to")
    print("  the smoothed prior, making pairs nearly indistinguishable. The method")
    print("  requires longer natural-language fragments to work as intended.\n")

    # ── Game L ──
    print("=== Game L: Linkage ===")
    true_groups = group_by_record(fragments)
    guessed_groups = memon_linkage_guess(
        fragments, text_map, model, vocab, N, D, n_records=len(true_groups)
    )
    p, r, f1 = eval_linkage(guessed_groups, true_groups)
    print(f"  Memon n-gram (n={N}, d={D})   precision={p:.4f}  recall={r:.4f}  f1={f1:.4f}")
    print(f"  NCD baseline                  precision=0.0117  recall=0.2400  f1=0.0223")
    print(f"  Random baseline               precision=~0.02   recall=~0.02   f1=~0.02")