import os
import json
import random
from itertools import combinations

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy.stats import kendalltau, norm

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # repo root
FRAGMENTS_PATH  = os.path.join(ROOT, "data", "identifier", "fragments.jsonl")
ANSWER_KEY_PATH = os.path.join(ROOT, "data", "identifier", "answer_key.jsonl")
RESULTS_DIR     = os.path.join(ROOT, "results")

N_RUNS = 23000


# ---------- loading ----------

def load_jsonl(path):
    records = []
    with open(path, "r") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def load_fragments(path):
    return load_jsonl(path)


def load_answer_key(path):
    rows = load_jsonl(path)
    by_record = {}
    for row in rows:
        by_record.setdefault(row["record_id"], []).append(row)

    true_order = {}
    for rec_id, frags in by_record.items():
        frags.sort(key=lambda r: r["position"])
        true_order[rec_id] = [r["fragment_id"] for r in frags]

    return true_order


def group_fragments_by_record(fragments):
    groups = {}
    for frag in fragments:
        groups.setdefault(frag["record_id"], []).append(frag["fragment_id"])
    return groups


# ---------- guessers ----------

def random_order_guess(fragment_ids):
    guess = fragment_ids[:]
    random.shuffle(guess)
    return guess


def random_linkage_guess(fragments, n_records):
    frag_ids = [f["fragment_id"] for f in fragments]
    random.shuffle(frag_ids)

    groups = {i: [] for i in range(n_records)}
    for idx, fid in enumerate(frag_ids):
        groups[idx % n_records].append(fid)

    return groups


# ---------- scoring ----------

def score_ordering(guessed_order, true_order):
    if set(guessed_order) != set(true_order):
        raise ValueError("guessed_order and true_order must contain the same IDs")

    true_rank = {fid: i for i, fid in enumerate(true_order)}
    guessed_rank_seq = [true_rank[fid] for fid in guessed_order]
    true_rank_seq = list(range(len(true_order)))

    result = kendalltau(guessed_rank_seq, true_rank_seq)
    return {"tau": result.statistic, "pvalue": result.pvalue}


def _pairs_from_groups(groups):
    pairs = set()
    for ids in groups.values():
        for a, b in combinations(sorted(ids), 2):
            pairs.add((a, b))
    return pairs


def score_linkage(guessed_groups, true_groups):
    guessed_pairs = _pairs_from_groups(guessed_groups)
    true_pairs = _pairs_from_groups(true_groups)

    precision = len(guessed_pairs & true_pairs) / len(guessed_pairs) if guessed_pairs else 0.0
    recall = len(guessed_pairs & true_pairs) / len(true_pairs) if true_pairs else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0

    return {"precision": precision, "recall": recall, "f1": f1}


# ---------- run (single trial) ----------

def run_game_o(fragments, true_order):
    grouped = group_fragments_by_record(fragments)
    taus = []
    for rec_id, frag_ids in grouped.items():
        guess = random_order_guess(frag_ids)
        result = score_ordering(guess, true_order[rec_id])
        # kendalltau returns nan for single-element records; skip those
        if not np.isnan(result["tau"]):
            taus.append(result["tau"])
    return sum(taus) / len(taus)


def run_game_l(fragments, true_order):
    true_groups = group_fragments_by_record(fragments)
    n_records = len(true_groups)

    guessed_groups = random_linkage_guess(fragments, n_records=n_records)
    return score_linkage(guessed_groups, true_groups)


# ---------- statistics helpers ----------

def summarize(name, values):
    arr = np.asarray(values, dtype=float)
    mu, sigma = arr.mean(), arr.std(ddof=1)
    low, high = mu - 2 * sigma, mu + 2 * sigma
    print(f"{name:>28}: mean={mu:.4f}  std={sigma:.4f}  "
          f"mean+/-2sd=[{low:.4f}, {high:.4f}]")
    return arr


def draw_normal_panel(ax, values, title, color):
    """Histogram (density) + fitted normal curve, with mean ± 2σ band."""
    mu, sigma = values.mean(), values.std(ddof=1)
    low, high = mu - 2 * sigma, mu + 2 * sigma
    ax.hist(values, bins=30, density=True, alpha=0.55, color=color,
            edgecolor="white", label="observed")
    if sigma > 0:
        xs = np.linspace(min(values.min(), low), max(values.max(), high), 300)
        ax.plot(xs, norm.pdf(xs, mu, sigma), "k-", lw=2,
                label=f"normal fit\nμ={mu:.4f}, σ={sigma:.4f}")
    ax.axvline(mu, color="red", ls="--", lw=1.5, label=f"mean={mu:.4f}")
    ax.axvspan(low, high, color="red", alpha=0.10,
               label=f"mean±2σ=[{low:.4f}, {high:.4f}]")
    ax.axvline(low, color="red", ls=":", lw=1)
    ax.axvline(high, color="red", ls=":", lw=1)
    ax.set_title(title)
    ax.set_xlabel("score")
    ax.set_ylabel("density")
    ax.legend(fontsize=8)


# ---------- main ----------

if __name__ == "__main__":
    fragments = load_fragments(FRAGMENTS_PATH)
    true_order = load_answer_key(ANSWER_KEY_PATH)

    print(f"Loaded {len(fragments)} fragments across {len(true_order)} records.")
    print(f"Running {N_RUNS} random baseline trials...\n")

    o_taus = []
    l_precision, l_recall, l_f1 = [], [], []

    for _ in range(N_RUNS):
        o_taus.append(run_game_o(fragments, true_order))
        res_l = run_game_l(fragments, true_order)
        l_precision.append(res_l["precision"])
        l_recall.append(res_l["recall"])
        l_f1.append(res_l["f1"])

    print("=== Summary over {} runs ===".format(N_RUNS))
    o_taus = summarize("Game O avg Kendall's tau", o_taus)
    l_precision = summarize("Game L precision", l_precision)
    l_recall = summarize("Game L recall", l_recall)
    l_f1 = summarize("Game L f1", l_f1)

    # ---------- Chart 1: normal distributions ----------
    fig1, axes = plt.subplots(1, 2, figsize=(13, 5))
    draw_normal_panel(axes[0], o_taus,
                      "Game O — avg Kendall's tau (n=%d)" % N_RUNS, "#4C72B0")
    draw_normal_panel(axes[1], l_f1,
                      "Game L — F1 score (n=%d)" % N_RUNS, "#55A868")
    fig1.suptitle("Random baseline: distribution of results with normal fit",
                  fontsize=14, fontweight="bold")
    fig1.tight_layout(rect=[0, 0, 1, 0.96])
    fig1.savefig(os.path.join(RESULTS_DIR, "baseline_normal_distribution.png"), dpi=130)
    print("\nSaved: baseline_normal_distribution.png")

    # ---------- Chart 2: box plots comparing metric variation ----------
    fig2, ax2 = plt.subplots(figsize=(9, 6))
    data = [o_taus, l_precision, l_recall, l_f1]
    labels = ["O: tau", "L: precision", "L: recall", "L: f1"]
    bp = ax2.boxplot(data, tick_labels=labels, showmeans=True, patch_artist=True)
    for patch, c in zip(bp["boxes"], ["#4C72B0", "#55A868", "#C44E52", "#8172B3"]):
        patch.set_facecolor(c)
        patch.set_alpha(0.6)
    ax2.axhline(0, color="gray", ls=":", lw=1)
    ax2.set_title("Variation of baseline metrics across %d runs" % N_RUNS,
                  fontweight="bold")
    ax2.set_ylabel("score")
    fig2.tight_layout()
    fig2.savefig(os.path.join(RESULTS_DIR, "baseline_boxplot.png"), dpi=130)
    print("Saved: baseline_boxplot.png")

    # ---------- Chart 3: per-run trace (variation over trials) ----------
    fig3, ax3 = plt.subplots(figsize=(12, 5))
    runs = np.arange(1, N_RUNS + 1)
    ax3.plot(runs, o_taus, color="#4C72B0", lw=0.8, alpha=0.8, label="O: tau")
    ax3.plot(runs, l_f1, color="#55A868", lw=0.8, alpha=0.8, label="L: f1")
    ax3.axhline(o_taus.mean(), color="#4C72B0", ls="--", lw=1.2)
    ax3.axhline(l_f1.mean(), color="#55A868", ls="--", lw=1.2)
    ax3.set_title("Per-run variation of baseline scores", fontweight="bold")
    ax3.set_xlabel("run #")
    ax3.set_ylabel("score")
    ax3.legend()
    fig3.tight_layout()
    fig3.savefig(os.path.join(RESULTS_DIR, "baseline_per_run_trace.png"), dpi=130)
    print("Saved: baseline_per_run_trace.png")
