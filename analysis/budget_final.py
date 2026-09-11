"""
budget_final.py — the FINAL price of the run, from what has been measured.

No API calls. Sources:
  MEASURED  pool 1: log(output tokens) = a + b log(fragments), fitted on each
            unit's final answer (77 O documents, 11 J pools); input tokens per
            prompt character. The live hierarchical sample: tokens per pair.
            The ledger: what has already been spent.
  EXACT     the grid J / O requests for pools 2-25 are BUILT here with the paid
            path's own builder; headline fragment counts come from
            data/prose/prose_fragments.jsonl (counts only, RUN_DECISIONS D2).
  FROZEN    the hierarchical k and its per-fragment pair rate
            (results/audit/hier_blocker_calibration.json, D8), its 12 headline
            pools (data/pools/hier_headline_12.json), the O samples (seeded,
            outcome-blind).

Expected = mean of one simulation that refits the token model on resampled
pool-1 answers every round and draws each request's residual; P95 = the 95th
percentile of the JOINT total of whatever lines are combined. An answer that
would exceed 128k is paid once at 128k and is a resource-bounded
non-completion (D6). The hierarchical attacker's expected cost uses its measured
tokens per pair; its bad case doubles its output (one live pool measured).

Every figure is API CREDIT. Out of pocket = credit x (1 + sales tax).

    python analysis/budget_final.py [--tax 0.08]
"""

import argparse
import hashlib
import json
import math
import os
import random
import statistics as st
import sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
os.chdir(ROOT)
for d in ("adversaries", "harness", "analysis"):
    sys.path.insert(0, os.path.join(ROOT, d))

from batch_game import build_spec, headline_docs, load_frame      # noqa: E402
from batch_submit import _latest_rows                              # noqa: E402
from run_ledger import Ledger                                      # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--tax", type=float, default=None, help="sales tax rate, e.g. 0.08")
ARGS = ap.parse_args()

B_IN, B_OUT = 1.0, 5.0          # sonnet-5 batch $/M
CAP = 128000
SIMS = 2000
WALL, TRIPWIRE = 167.0, 120.0   # the wall is OUT OF POCKET
OVERHEAD_EXP, OVERHEAD_P95 = 0.06, 0.15      # repairs (pool 1: 4 of 88 units)
SPENT = Ledger().observed

KEEP = ["random__sentence", "random__clause", "random__token-window",
        "semantic__sentence", "semantic__clause",
        "coherence-sever__clause", "coherence-sever__token-window",
        "subject-verb__sentence", "subject-verb__clause"]
REF = "semantic__sentence"
HEAD_O_DOCS, GRID_O_DOCS, GRID_O_EXT = 100, 30, 60
BANDS = [(1, 15), (16, 30), (31, 60), (61, 100), (101, 10 ** 9)]


def seeded(keys, salt):
    return sorted(keys, key=lambda k: hashlib.sha256(f"{salt}|{k}".encode()).hexdigest())


# ── the token model, from pool 1 ─────────────────────────────────────────────
spec1 = json.load(open("runs/grid_A_pool1.json", encoding="utf-8"))
rows1 = _latest_rows(["results/batches/grid-A-pool1_reused.jsonl"] + [
    f"results/batches/{t}.results.jsonl"
    for t in ("grid-A-pool1", "grid-A-pool1-rs1", "grid-A-pool1-rs2")])
pts = {"O": [], "J": []}
chars = in_tok = 0
for cid, s in spec1["sidecar"].items():
    r = rows1[cid]
    pts[s["game"]].append((s["n_fragments"], r["usage"]["output_tokens"]))
    chars += len(s["prompt"])
    in_tok += r["usage"]["input_tokens"]
TOK_PER_CHAR = in_tok / chars


def fit(points):
    xs = [math.log(n) for n, _ in points]
    ys = [math.log(t) for _, t in points]
    mx, my = st.mean(xs), st.mean(ys)
    b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sum((x - mx) ** 2 for x in xs)
    a = my - b * mx
    return a, b, [y - (a + b * x) for x, y in zip(xs, ys)]


# ── the requests ─────────────────────────────────────────────────────────────
frame = load_frame("data/pools/pools.json", "data/pools/linkage_grid.json")
rest = frame[1:]                                   # pools 2-25
o_all = [m for _p, ms in rest for m in ms]
grid = build_spec([os.path.join("results", "grid_A", c) for c in KEEP], ["O", "J"],
                  docs=len(o_all), pool_size=7, seed=42, tag="budget-only",
                  pools=rest, o_docs=o_all, forbid_docs=headline_docs())
units = defaultdict(list)                          # cell -> [(game, unit, n, chars)]
for s in grid["sidecar"].values():
    units[s["cell"]].append((s["game"], s["unit"], s["n_fragments"], len(s["prompt"])))
o_order = seeded(o_all, "grid-O-60")               # the 30 are the first 30 of the 60
o30, o60 = set(o_order[:GRID_O_DOCS]), set(o_order[:GRID_O_EXT])

grid_ids = {p for p, _ in frame}
head_pools = [(p, ms) for p, ms in load_frame("data/pools/pools.json") if p not in grid_ids]
nfr = Counter(json.loads(l)["record_id"] for l in
              open("data/prose/prose_fragments.jsonl", encoding="utf-8") if l.strip())
cpf = {g: st.mean(c / n for gg, _u, n, c in units[REF] if gg == g) for g in ("O", "J")}
head_docs_all = [m for _p, ms in head_pools for m in ms]
pool_n = {p: sum(nfr[m] for m in ms) for p, ms in head_pools}


def head_o_sample(k):
    """Proportional to each length band, largest remainder; seeded within bands."""
    by = {b: [d for d in head_docs_all if b[0] <= nfr[d] <= b[1]] for b in BANDS}
    q = {b: k * len(v) / len(head_docs_all) for b, v in by.items()}
    take = {b: int(x) for b, x in q.items()}
    for b in sorted(q, key=lambda b: -(q[b] - take[b]))[:k - sum(take.values())]:
        take[b] += 1
    return [d for b, v in by.items() for d in seeded(v, f"headline-O-{k}")[:take[b]]]


def o_req(keep_set):
    return [(g, n, c) for cl in KEEP for g, u, n, c in units[cl] if g == "O" and u in keep_set]


ref_j = [(g, n, c) for g, _u, n, c in units[REF] if g == "J"]
ref_o = [(g, n, c) for g, _u, n, c in units[REF] if g == "O"]
LINES = {f"gridJ:{cl}": [(g, n, c) for g, _u, n, c in units[cl] if g == "J"] for cl in KEEP}
LINES.update({
    "headJ": [("J", pool_n[p], int(cpf["J"] * pool_n[p])) for p, _ in head_pools],
    "headO": [("O", nfr[d], int(cpf["O"] * nfr[d])) for d in head_o_sample(HEAD_O_DOCS)],
    "gridO30": o_req(o30),
    "gridO_ext": o_req(o60 - o30),
    "rep_small": ref_j[:12] + ref_o[:60],
    "rep_full": (ref_j + ref_o) * 2,
})
GRID_J = [f"gridJ:{cl}" for cl in KEEP]

# ── the hierarchical attacker and G3: priced from measurement, not simulated ─
CAL = json.load(open("results/audit/hier_blocker_calibration.json", encoding="utf-8"))
HIER_K = CAL["chosen_k"]
IN_PP, OUT_PP = CAL["cost_basis"]["in_tok_per_pair"], CAL["cost_basis"]["out_tok_per_pair"]
PPF = {int(k): v["pairs_per_fragment"] for k, v in CAL["results"].items()}
HP = json.load(open("data/pools/hier_headline_12.json", encoding="utf-8"))


def hier_usd(pools, k=HIER_K, out_mult=1.0):
    return sum(PPF[k] * pool_n[p] * (IN_PP / 1e6 * B_IN + OUT_PP * out_mult / 1e6 * B_OUT)
               for p in pools)


G3_RESULTS = "results/batches/g3-control.results.jsonl"
if os.path.exists(G3_RESULTS):
    G3 = (0.0, 0.0, "run -- its actual cost is inside 'already spent'")
elif os.path.exists("runs/g3_control.json"):
    e = json.load(open("runs/g3_control.json", encoding="utf-8"))["expected_usd"]
    G3 = (e, 2 * e, "estimate from its frozen spec")
else:
    G3 = (2.0, 2.6, "estimate")
DET = {"g3": G3[:2],
       "hier12": (hier_usd(HP["pool_ids"]), hier_usd(HP["pool_ids"], out_mult=2.0)),
       "hier8": (hier_usd(HP["extension_to_20"]), hier_usd(HP["extension_to_20"], out_mult=2.0))}


# ── one joint simulation over every simulated line ───────────────────────────
def one_round(reqs, f, rng):
    usd, rbnc = 0.0, 0
    for g, n, c in reqs:
        a, b, res = f[g]
        t = math.exp(a + b * math.log(n) + rng.choice(res))
        usd += c * TOK_PER_CHAR / 1e6 * B_IN
        if t > CAP:                    # D6: paid once at the ceiling, never re-asked
            rbnc += 1
            t = CAP
        usd += t / 1e6 * B_OUT
    return usd, rbnc


rng = random.Random(7)
COST = {k: [] for k in LINES}
RBNC = {k: 0.0 for k in LINES}
for _ in range(SIMS):
    f = {g: fit([rng.choice(p) for _ in p]) for g, p in pts.items()}
    for k, reqs in LINES.items():
        u, c = one_round(reqs, f, rng)
        COST[k].append(u)
        RBNC[k] += c / SIMS


def p95(xs):
    return sorted(xs)[int(0.95 * len(xs))]


def joint(keys):
    if not keys:
        return 0.0, 0.0
    tot = [sum(v) for v in zip(*(COST[k] for k in keys))]
    return st.mean(tot) * (1 + OVERHEAD_EXP), p95(tot) * (1 + OVERHEAD_P95)


# ── the price ────────────────────────────────────────────────────────────────
PARTS = [
    ("G3 masking side-channel diagnostic (dev pool)", [], "g3"),
    ("Headline J, 46 pools", ["headJ"], None),
    ("Grid J, 9 cells x pools 2-25 (216 pools)", GRID_J, None),
    (f"Hierarchical, 12 prespecified headline pools, k={HIER_K}", [], "hier12"),
    (f"Headline O, {HEAD_O_DOCS} docs, length-stratified", ["headO"], None),
    (f"Grid O, {GRID_O_DOCS} docs/cell x 9 cells", ["gridO30"], None),
]
OPTIONAL = [
    ("Hierarchical +8 -> 20 pools", [], "hier8"),
    (f"Grid O +{GRID_O_EXT - GRID_O_DOCS} -> {GRID_O_EXT} docs/cell", ["gridO_ext"], None),
    ("Repeats, small (reference x1, 12 pools J + 60 docs O)", ["rep_small"], None),
    ("Repeats, full (reference x2, pools 2-25)", ["rep_full"], None),
]
W = 58
print("FINAL PRICE -- API credit, before sales tax")
print(f"  already spent (ledger, observed): ${SPENT:.2f}")
print(f"  hierarchical: k={HIER_K} (D8; coverage inadequate at every k), measured "
      f"{IN_PP:.0f} in / {OUT_PP:.0f} out tokens per pair; 12 pools {HP['pool_ids'][:3]}...")
print(f"  G3: {G3[2]}\n")
print(f"{'part':<{W}}{'expected':>10}{'P95':>10}{'non-compl.':>12}")


def part_row(label, keys, det):
    e, p = joint(keys)
    if det:
        e, p = e + DET[det][0], p + DET[det][1]
    rb = sum(RBNC[k] for k in keys)
    print(f"  {label:<{W - 2}}{e:>10.2f}{p:>10.2f}{rb:>12.1f}")
    return e, p


for label, keys, det in PARTS:
    part_row(label, keys, det)
print("  optional extensions:")
for label, keys, det in OPTIONAL:
    part_row("  " + label, keys, det)
for k in sorted(PPF):
    print(f"    (hierarchical 12 pools at k={k}: ${hier_usd(HP['pool_ids'], k=k):.2f} expected)")

print(f"\nRUN ORDER, cumulative (already spent included)")
print(f"  {'step':<{W}}{'expected':>10}{'P95':>10}{'left under wall (exp / P95)':>30}")
acc_keys, acc_det = [], []
for i, (label, keys, det) in enumerate(PARTS + OPTIONAL):
    acc_keys += keys
    if det:
        acc_det.append(det)
    e, p = joint(acc_keys)
    e = SPENT + e + sum(DET[d][0] for d in acc_det)
    p = SPENT + p + sum(DET[d][1] for d in acc_det)
    tag = f"{i}" if i < len(PARTS) else f"{i} (opt)"
    print(f"  {tag + ' ' + label:<{W}}{e:>10.2f}{p:>10.2f}{WALL - e:>15.2f} / {WALL - p:>7.2f}")
    if i == len(PARTS) - 1:
        req_e, req_p = e, p
        print(f"  {'-- REQUIRED TOTAL (steps 0-5) --':<{W}}{e:>10.2f}{p:>10.2f}{WALL - e:>15.2f} / {WALL - p:>7.2f}")

print("\nDROP ORDER if the forecast worsens: repeats full -> repeats small -> grid O extension ->"
      " hierarchical extension -> grid O 30 -> headline O -> hierarchical 12 -> grid J pools from"
      " the end of the pool order. Headline J is never dropped.")

print("\nTAX: the wall is out of pocket, so the ledger's hard limit in credit is $167 / (1 + tax).")
rates = [ARGS.tax] if ARGS.tax is not None else [0.0, 0.05, 0.08, 0.10]
for t in rates:
    print(f"  tax {t:>5.1%}: hard limit ${WALL / (1 + t):.2f} credit; required total out of pocket "
          f"${req_e * (1 + t):.2f} expected / ${req_p * (1 + t):.2f} P95; "
          f"{'fits' if req_p <= WALL / (1 + t) else ('expected fits, P95 over' if req_e <= WALL / (1 + t) else 'OVER')}")
