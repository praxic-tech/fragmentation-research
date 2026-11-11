"""
game_j_adjacency.py — the two free Game J measurements. NO API CALLS.

Both exist because of an audit finding: the headline game J surface reports the
FULL within-document precedence relation and has no adjacency or readability
measurement at all (`reconstruction_detail` is populated for 0 of 1,168 game J
rows in MASTER_RESULTS.csv -- it needs one document's fragment list, which is a
game O object). And the only reference on prose game J is the analytic
one-bucket baseline, which is not a legal answer to a prompt demanding exactly
N groups.

1. ADJACENCY AND CONTIGUITY
   `joint_metrics.ordered_pairs` emits every (earlier, later) pair inside a
   group. So F1_J can be high while almost nothing sits next to its true
   neighbour. This module adds the immediate-adjacency surface:

       predicted adjacency pairs   (g[i], g[i+1]) for each predicted group
       true adjacency pairs        (t[i], t[i+1]) for each true record
       adj_F1                      the usual F1 over those two sets

   A pair spanning two documents is simply a false positive. We do NOT adopt
   Paixao et al.'s convention of counting the seam between two completed
   documents as correct -- that exists because their output is one global
   permutation in which document order is meaningless. Ours is a partition, so
   a cross-document adjacency is a membership error and is scored as one.

   Contiguity: walking a predicted group in its predicted order, a LINK is two
   consecutive entries that are from the same record AND adjacent in that
   record's true order. The longest chain of links is the longest intact
   stretch of real text the attacker gets back. An interloper from another
   document breaks the run, which is the honest reading for a privacy claim.

2. A VALID RANDOM BASELINE (prose game J has none; identifier J and game O do)
   size-blind (PRIMARY)  shuffle, deal round-robin into N groups. The attacker
                         is told N but NOT the true group sizes -- prompt_J says
                         only that records "may contain different numbers of
                         fragments" -- so a baseline handed the true sizes would
                         know more than the attacker does. Same dealing rule as
                         the identifier Random baseline (D11/D13).
   oracle-size           shuffle, cut into the TRUE per-document sizes.
                         ATTACKER-FAVOURABLE. Reported separately, never as the
                         chance level.

Scoring conventions are inherited, not reimplemented: fragments the attacker
placed nowhere become singleton groups (score_row's reading), and F1_J / F1_L /
q come from joint_metrics.decompose.

TWO VERIFICATIONS, both run 2026-11-05
--------------------------------------
1. score_fast's combinatorial counts are asserted equal to
   joint_metrics.decompose (C, K, F1_J, F1_L, b_J to 1e-9) on the first eight
   real attacker answers of every run. Not a sanity check -- it fails the run.
2. The random baseline's C = K/2 shortcut was cross-checked against a full
   1,000-draw run that ENUMERATED concordant pairs instead. Headline size-blind
   F1_J 0.0771 (analytic order) vs 0.0772 (enumerated); adjacency F1, longest
   run, run fraction and the no-intact-pair count identical to 4 dp; grid rows
   identical (0.0721 size-blind, 0.0749 oracle-size). The 1e-4 residual is the
   sampling noise the analytic treatment removes.

Timing note: 1,000 draws over all 262 prose pools is ~6 minutes with the
precomputed PoolTruth. The first version, which rebuilt the truth pair sets and
re-derived the analytic baseline inside every draw, did not finish in hours.

    python analysis/game_j_adjacency.py [--draws N]
"""

import csv
import hashlib
import json
import os
import random
import statistics as st
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
os.chdir(ROOT)
for d in ("adversaries", "harness", "analysis"):
    sys.path.insert(0, os.path.join(ROOT, d))

from joint_game import _as_groups, build_units            # noqa: E402
from joint_metrics import decompose                       # noqa: E402

NAMESPACE = "game-j-adjacency-v1"
SEED = 42
DEFAULT_DRAWS = 1000
OUT = os.path.join("results", "final_analysis", "GAME_J_ADJACENCY.csv")

J_SPECS = {"headline": ["runs/final_headlineJ.json"],
           "grid": [f"runs/final_gridJ_w{k}.json" for k in (1, 2, 3, 4)]}
RESULT_DIR = {"headline": "headlineJ", "grid": "gridJ"}
DESIGNATION = {"headline": "headline", "grid": "primary"}
EMB = "Embedding (post-hoc exploratory)"


# ── the adjacency surface ────────────────────────────────────────────────────

def adjacency_pairs(groups):
    """Immediate directed pairs implied by an ordered partition."""
    out = set()
    for g in groups:
        for a, b in zip(g, g[1:]):
            out.add((a, b))
    return out


def adjacency_score(groups, truth_lists):
    """Precision / recall / F1 over immediate directed within-document pairs.

    A cross-document adjacency is not in truth, so it costs precision. No free
    seams.
    """
    guessed = adjacency_pairs(groups)
    true = adjacency_pairs(truth_lists)
    tp = len(guessed & true)
    p = tp / len(guessed) if guessed else 0.0
    r = tp / len(true) if true else 0.0
    return {"adj_tp": tp, "adj_n_guessed": len(guessed), "adj_n_true": len(true),
            "adj_precision": p, "adj_recall": r,
            "adj_f1": (2 * p * r / (p + r)) if (p + r) else 0.0}


def contiguity(groups, truth_order):
    """Longest intact run of real text, per true record.

    truth_order : {record_id: [fragment ids in true order]}
    Returns the mean and max longest-run over the pool's records, the mean run
    FRACTION (longest run / that record's length), and how many records came
    back with no intact pair at all.
    """
    rec_of, pos_of, length = {}, {}, {}
    for rid, ids in truth_order.items():
        length[rid] = len(ids)
        for i, f in enumerate(ids):
            rec_of[f] = rid
            pos_of[f] = i

    best = {rid: 1 if length[rid] else 0 for rid in truth_order}
    for g in groups:
        run_rec, run_len = None, 1
        for a, b in zip(g, g[1:]):
            linked = (rec_of.get(a) is not None
                      and rec_of.get(a) == rec_of.get(b)
                      and pos_of[b] == pos_of[a] + 1)
            if linked:
                rid = rec_of[a]
                run_len = run_len + 1 if run_rec == rid else 2
                run_rec = rid
                if run_len > best[rid]:
                    best[rid] = run_len
            else:
                run_rec, run_len = None, 1

    runs = [best[rid] for rid in truth_order]
    fracs = [best[rid] / length[rid] for rid in truth_order if length[rid]]
    return {"mean_longest_run": st.fmean(runs) if runs else 0.0,
            "max_longest_run": max(runs) if runs else 0,
            "mean_run_fraction": st.fmean(fracs) if fracs else 0.0,
            "records_with_no_intact_pair": sum(1 for r in runs if r <= 1),
            "n_records": len(runs)}


class PoolTruth:
    """Everything about one pool's answer key, computed ONCE.

    The first version of this module called joint_metrics.decompose per draw,
    which rebuilt the truth pair sets and re-derived the analytic baseline
    10,000 times over for a single pool. Here the truth side is built once and
    the per-draw work is counted combinatorially instead of by materialising
    sets: for a partition,

        |guessed unordered pairs| = sum over groups of C(|g|, 2)
        K = sum over (group, record) of C(|g & r|, 2)
        C = concordant pairs inside each (group, record) overlap

    which is exact and touches sum |g & r|^2 elements rather than the full
    O(n^2) pair sets. Verified against decompose() in main().
    """

    def __init__(self, truth_order, members):
        self.members = list(members)
        self.truth_lists = [truth_order[r] for r in self.members]
        self.t_adj = adjacency_pairs(self.truth_lists)
        self.rec_of, self.pos_of, self.length = {}, {}, {}
        for rid in self.members:
            ids = truth_order[rid]
            self.length[rid] = len(ids)
            for i, f in enumerate(ids):
                self.rec_of[f] = rid
                self.pos_of[f] = i
        sizes = [self.length[r] for r in self.members]
        m, t = sum(sizes), sum(s * (s - 1) // 2 for s in sizes)
        p = m * (m - 1) // 2
        self.n_t_un = t
        self.b_joint = t / (p + t) if (p + t) else 0.0


def score_fast(groups, pt, random_order=False):
    """Precedence, adjacency and contiguity for one answer. Exact.

    random_order=True is for the random baselines ONLY. Given a sampled
    partition, the within-group order is uniformly random, so the concordant
    count has the exact expectation C = K/2 -- every correctly co-clustered
    pair points the right way with probability one half. Taking that
    expectation instead of enumerating concordant pairs removes the one
    O(sum |g & r|^2) step in the loop, and it is also LESS noisy than sampling
    it: this is the same argument joint_metrics.analytic_baseline makes for
    preferring the closed form ("Sampling it instead was measurably noisy").
    The partition, adjacency and contiguity are still sampled, because those do
    depend on the draw.
    """
    n_g_un = sum(len(g) * (len(g) - 1) // 2 for g in groups)
    c = k = 0
    for g in groups:
        if len(g) < 2:
            continue
        by_rec = defaultdict(list)
        for f in g:                          # guessed order preserved
            rid = pt.rec_of.get(f)
            if rid is not None:
                by_rec[rid].append(pt.pos_of[f])
        for pos in by_rec.values():
            m = len(pos)
            if m < 2:
                continue
            k += m * (m - 1) // 2
            if not random_order:
                c += sum(1 for i in range(m) for j in range(i + 1, m) if pos[i] < pos[j])
    if random_order:
        c = k / 2.0

    denom = n_g_un + pt.n_t_un
    f1j = 2 * c / denom if denom else 0.0
    f1l = 2 * k / denom if denom else 0.0
    row = {"F1_J": f1j, "F1_L": f1l, "q": (c / k) if k else None,
           "C": c, "K": k, "b_J": pt.b_joint,
           "A_J": ((f1j - pt.b_joint) / (1.0 - pt.b_joint)
                   if pt.b_joint < 1 else float("nan"))}
    row.update(adjacency_score(groups, pt.truth_lists))
    row.update(contiguity_fast(groups, pt))
    return row


def contiguity_fast(groups, pt):
    """contiguity(), against a precomputed PoolTruth."""
    best = {rid: 1 if pt.length[rid] else 0 for rid in pt.members}
    for g in groups:
        run_rec, run_len = None, 1
        for a, b in zip(g, g[1:]):
            ra = pt.rec_of.get(a)
            if ra is not None and ra == pt.rec_of.get(b) and pt.pos_of[b] == pt.pos_of[a] + 1:
                run_len = run_len + 1 if run_rec == ra else 2
                run_rec = ra
                if run_len > best[ra]:
                    best[ra] = run_len
            else:
                run_rec, run_len = None, 1
    runs = [best[r] for r in pt.members]
    fracs = [best[r] / pt.length[r] for r in pt.members if pt.length[r]]
    return {"mean_longest_run": st.fmean(runs) if runs else 0.0,
            "max_longest_run": max(runs) if runs else 0,
            "mean_run_fraction": st.fmean(fracs) if fracs else 0.0,
            "records_with_no_intact_pair": sum(1 for r in runs if r <= 1),
            "n_records": len(runs)}


def full_row(groups, truth_order, members):
    """Every surface for one answer: precedence, adjacency, contiguity."""
    return score_fast(groups, PoolTruth(truth_order, members))


def pad_singletons(groups, all_ids):
    """score_row's convention: anything placed nowhere becomes its own group."""
    seen, out = set(), []
    for g in groups:
        h = [f for f in g if f in all_ids and f not in seen]
        seen.update(h)
        if h:
            out.append(h)
    out += [[f] for f in sorted(all_ids) if f not in seen]
    return out


# ── the random baselines ─────────────────────────────────────────────────────

def _rng(pool_id, variant):
    h = hashlib.sha256(f"{NAMESPACE}|{pool_id}|{variant}|{SEED}".encode("utf-8")).hexdigest()
    return random.Random(int(h[:16], 16))


def random_baseline(all_ids, truth_order, members, pool_id, variant, draws):
    """Mean over `draws` seeded draws of a VALID N-group partition.

    variant "size-blind"  : round-robin deal into N groups (sizes not supplied)
    variant "oracle-size" : cut into the TRUE per-document sizes
                            (ATTACKER-FAVOURABLE)
    """
    rng = _rng(pool_id, variant)
    ids = sorted(all_ids)
    n = len(members)
    sizes = [len(truth_order[r]) for r in members] if variant == "oracle-size" else None
    pt = PoolTruth(truth_order, members)          # built ONCE, not per draw

    acc, qs, Cs, Ks = defaultdict(float), [], 0, 0
    for _ in range(draws):
        rng.shuffle(ids)
        if sizes is None:
            groups = [ids[i::n] for i in range(n)]
        else:
            groups, k = [], 0
            for s in sizes:
                groups.append(ids[k:k + s])
                k += s
        r = score_fast(groups, pt, random_order=True)
        for key, v in r.items():
            if key in ("q", "C", "K"):
                continue
            acc[key] += v
        Cs += r["C"]
        Ks += r["K"]
        if r["q"] is not None:
            qs.append(r["q"])
    out = {k: v / draws for k, v in acc.items()}
    out.update({"q": st.fmean(qs) if qs else None, "C": Cs / draws, "K": Ks / draws,
                "q_micro": (Cs / Ks) if Ks else None,
                "expectation": f"mean of {draws} seeded partition draws ({variant}); C=K/2 exact over within-group order"})
    return out


# ── main ─────────────────────────────────────────────────────────────────────

def cell_name(cell_dir):
    base = os.path.basename(os.path.normpath(cell_dir))
    return "semantic__sentence (full length)" if base == "prose" else base


_checked = 0


def main(draws=DEFAULT_DRAWS):
    rows = []
    for fam, paths in J_SPECS.items():
        for path in paths:
            b = json.load(open(path, encoding="utf-8"))["build"]
            for cell_dir in b["cells"]:
                base = os.path.basename(os.path.normpath(cell_dir))
                rdir = os.path.join("results", "final", RESULT_DIR[fam], base)
                sonnet = {r["unit"]: r for r in (json.loads(l) for l in
                          open(os.path.join(rdir, "J.jsonl"), encoding="utf-8") if l.strip())}
                mp = os.path.join("results", "final_free", RESULT_DIR[fam],
                                  f"{base}.memon_joint.jsonl")
                memon = {r["pool"]: r for r in (json.loads(l) for l in
                         open(mp, encoding="utf-8") if l.strip())} if os.path.exists(mp) else {}
                ep = os.path.join("results", "final_embedding", RESULT_DIR[fam],
                                  f"{base}.embedding_joint.jsonl")
                emb = {r["pool"]: r for r in (json.loads(l) for l in
                       open(ep, encoding="utf-8") if l.strip())} if os.path.exists(ep) else {}

                for pid, members in b["pools"]:
                    _o, units, _key, truth = build_units(cell_dir, 0, len(members), SEED,
                                                         pools=[(pid, members)], o_docs=[])
                    (_p, frags, _n), = units
                    tg = truth[pid]
                    all_ids = {i for v in tg.values() for i in v}
                    common = {"corpus": "prose", "family": fam,
                              "designation": DESIGNATION[fam], "cell": cell_name(cell_dir),
                              "unit_id": pid, "n_fragments": len(frags),
                              "n_docs": len(members)}

                    def emit(attacker, groups, extra=None):
                        g = pad_singletons(groups, all_ids)
                        r = full_row(g, tg, members)
                        # the combinatorial counts must equal joint_metrics.decompose
                        global _checked
                        if _checked < 8:
                            d = decompose(g, tg, list(members))
                            for a, b, nm in ((r["C"], d["C"], "C"), (r["K"], d["K"], "K"),
                                             (r["F1_J"], d["f1_joint"], "F1_J"),
                                             (r["F1_L"], d["f1_linkage"], "F1_L"),
                                             (r["b_J"], d["baseline_joint"], "b_J")):
                                assert abs(a - b) < 1e-9, f"{nm}: fast {a} vs decompose {b}"
                            _checked += 1
                        rows.append({**common, "attacker": attacker, **r, **(extra or {})})

                    s = sonnet.get(pid)
                    if s is not None:
                        g = _as_groups(s["raw_response"])
                        g = [[s["alias_map"][l] for l in grp if l in s["alias_map"]] for grp in g]
                        emit("One-shot Sonnet", [x for x in g if x])
                    if pid in memon:
                        emit("Memon-inspired", memon[pid]["reconstruction"])
                    if pid in emb:
                        emit(EMB, emb[pid]["reconstruction"])

                    for variant, label in (("size-blind", "Random valid N-group (size-blind)"),
                                           ("oracle-size",
                                            "Random valid N-group (oracle-size, ATTACKER-FAVOURABLE)")):
                        rb = random_baseline(all_ids, tg, members, pid, variant, draws)
                        rows.append({**common, "attacker": label, **rb})
                    print(f"  {fam:8s} {base:28s} {pid}  n={len(frags)}", flush=True)

    cols, seen = [], set()
    for r in rows:
        for k in r:
            if k not in seen:
                seen.add(k)
                cols.append(k)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow(r)
    print(f"\nwrote {OUT}  ({len(rows)} rows, {draws} draws per baseline)")
    summarise(rows)


def summarise(rows):
    for desig in ("headline", "primary"):
        sub = [r for r in rows if r["designation"] == desig]
        if not sub:
            continue
        print(f"\n{'='*94}\n{desig.upper()}  (n units = {len({r['unit_id']+r['cell'] for r in sub})})\n{'='*94}")
        print(f"{'attacker':52s} {'F1_J':>7s} {'adj_F1':>7s} {'longrun':>8s} {'runfrac':>8s} {'noPair':>7s}")
        for a in sorted({r["attacker"] for r in sub}):
            s = [r for r in sub if r["attacker"] == a]
            def m(k):
                v = [r[k] for r in s if r.get(k) is not None]
                return st.fmean(v) if v else float("nan")
            print(f"{a:52s} {m('F1_J'):7.4f} {m('adj_f1'):7.4f} "
                  f"{m('mean_longest_run'):8.2f} {m('mean_run_fraction'):8.4f} "
                  f"{m('records_with_no_intact_pair'):7.2f}")


if __name__ == "__main__":
    d = DEFAULT_DRAWS
    if "--draws" in sys.argv:
        d = int(sys.argv[sys.argv.index("--draws") + 1])
    main(d)
