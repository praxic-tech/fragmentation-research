"""
fig_fragment_length.py — fragment length vs reconstruction advantage. NO API CALLS.

Emits docs/figures/fragment_length_vs_advantage.svg and prints the table that
docs/FRAGMENT_LENGTH_RESULTS.md carries.

Two families on one pair of axes, because the comparison is the point:

  CONTROLLED GRADIENT (D16 + D18)  the same 20 pools, the same 140 four-sentence
      excerpts, byte-identical text. Only the cut width changes, so mean
      fragment length is the ONLY variable and the points are ordered along x.
      Drawn as a connected line.
  MAIN GRID (D9-D13)  full-length clinical documents, 4 cutting strategies x
      3 granularity labels. Fragment length is a CONSEQUENCE of the strategy,
      not a controlled input, so the points are unordered in x. Drawn as
      markers only, never joined.

The two families are NOT on a common footing: grid documents average 478 words
(659 for the headline cell) against 76 for the excerpts, so a grid point and a
gradient point at the same x differ in how many fragments a pool holds and how
much context each document carries. The chart marks them separately and the
doc says so; do not fit one curve through both.

y is A_J, the advantage over the analytic one-bucket reference, per pool then
averaged (joint_metrics.advantage). y = 0 is that reference, drawn explicitly.

Sources, all committed:
  grid + headline   results/final_analysis/MASTER_RESULTS.csv (One-shot Sonnet)
  gradient arms     results/final/gradientJ/REPORT.txt, via MASTER-equivalent
                    recomputation in results/gradient/ (w4/w3/w2)
  D16 anchors       results/single_token_edge/analysis/{summary.json,per_pool.csv}
  fragment lengths  measured from each cell's prose_fragments.jsonl

Palette: dataviz reference instance, categorical slots 1-2 (blue #2a78d6,
orange #eb6834). Validated with scripts/validate_palette.js --mode light
--pairs all: all checks pass, CVD dE 24.7, normal-vision dE 33.6, contrast >=3:1.

    python analysis/fig_fragment_length.py
"""

import csv
import json
import math
import os
import statistics as st

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
OUT = os.path.join("docs", "figures", "fragment_length_vs_advantage.svg")

SURFACE, INK, INK2, INK3 = "#fcfcfb", "#0b0b0b", "#52514e", "#8a8984"
S1, S2 = "#2a78d6", "#eb6834"          # categorical slots 1 and 2
GRID = "#e4e3df"

# the gradient arms: (label, cell dir, A_J) -- A_J from the frozen analyses
GRADIENT = [
    ("sentence", "results/single_token_edge/edge__sentence", 0.5387),
    ("4-word",   "results/gradient/edge__w4",               0.3127),
    ("3-word",   "results/gradient/edge__w3",               0.2178),
    ("2-word",   "results/gradient/edge__w2",               0.0812),
    ("1-word",   "results/single_token_edge/edge__token",  -0.0165),
]
SHORT = {"coherence-sever": "CS", "random": "R", "semantic": "SE", "subject-verb": "SV"}
GRAN = {"sentence": "sent", "clause": "clause", "token-window": "tok-win"}


def frag_words(cell_dir):
    rows = [json.loads(l) for l in
            open(os.path.join(cell_dir, "prose_fragments.jsonl"), encoding="utf-8") if l.strip()]
    wl = [len(r["text"].split()) for r in rows]
    docs = {}
    for r in rows:
        docs.setdefault(r["record_id"], []).append(len(r["text"].split()))
    return {"n": len(wl), "mean": st.fmean(wl), "median": st.median(wl),
            "sd": st.pstdev(wl), "min": min(wl), "max": max(wl),
            "frags_per_doc": st.fmean([len(v) for v in docs.values()]),
            "doc_words": st.fmean([sum(v) for v in docs.values()])}


def grid_cells():
    rows = [r for r in csv.DictReader(open("results/final_analysis/MASTER_RESULTS.csv",
                                           encoding="utf-8"))
            if r["game"] == "J" and r["corpus"] == "prose"
            and r["attacker"] == "One-shot Sonnet"]

    def num(v):
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    out = []
    for cell in sorted({r["cell"] for r in rows}):
        c = [r for r in rows if r["cell"] == cell]

        def m(k):
            v = [num(r[k]) for r in c if num(r[k]) is not None]
            return st.fmean(v) if v else float("nan")

        out.append({"cell": cell, "strategy": c[0]["strategy"],
                    "granularity": c[0]["granularity"], "n": len(c),
                    "words": m("frag_words_mean"), "median": m("frag_words_median"),
                    "frags_per_doc": m("frags_per_doc"), "doc_words": m("doc_words_mean"),
                    "A_J": m("A_J"), "F1_J": m("F1_J"), "F1_L": m("F1_L"), "q": m("q")})
    return out


# ── geometry ────────────────────────────────────────────────────────────────
W, H = 900, 790
L, R, T, B = 74, 26, 92, 88
PW, PH = W - L - R, 300          # panel 1
T2, PH2 = T + PH + 92, 196                        # panel 2
XLO, XHI = math.log10(0.88), math.log10(25.0)
YLO, YHI = -0.12, 0.86
R2LO, R2HI = 0.0, 70.0                            # panel 2, percent of document


def px(w):
    return L + (math.log10(w) - XLO) / (XHI - XLO) * PW


def py(a):
    return T + (YHI - a) / (YHI - YLO) * PH


def py2(v):
    return T2 + (R2HI - v) / (R2HI - R2LO) * PH2


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def main():
    grad = [{"label": lbl, "A_J": a, **frag_words(d)} for lbl, d, a in GRADIENT]
    grid = grid_cells()

    s = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
         f'viewBox="0 0 {W} {H}" font-family="Inter, -apple-system, Segoe UI, Helvetica, Arial, sans-serif">',
         f'<rect width="{W}" height="{H}" fill="{SURFACE}"/>']

    s.append(f'<text x="{L}" y="30" font-size="16.5" font-weight="600" fill="{INK}">'
             'Fragment length against reconstruction advantage</text>')
    s.append(f'<text x="{L}" y="51" font-size="12.5" fill="{INK2}">'
             'One-shot Sonnet, game J. y = 0 is the analytic one-bucket reference. '
             'Log x. The two families are not on a common footing — see note.</text>')

    # y gridlines
    for a in (-0.1, 0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8):
        y = py(a)
        zero = abs(a) < 1e-9
        s.append(f'<line x1="{L}" y1="{y:.1f}" x2="{L+PW}" y2="{y:.1f}" '
                 f'stroke="{INK3 if zero else GRID}" stroke-width="{1.4 if zero else 1}" '
                 f'{"" if zero else ""}/>')
        s.append(f'<text x="{L-9}" y="{y+4:.1f}" font-size="11.5" text-anchor="end" '
                 f'fill="{INK2 if zero else INK3}">{a:+.1f}</text>')
    s.append(f'<text x="{L+PW}" y="{py(0)-8:.1f}" font-size="11" text-anchor="end" '
             f'fill="{INK2}">one-bucket reference</text>')

    # x ticks
    for w in (1, 2, 3, 4, 6, 10, 15, 20):
        x = px(w)
        s.append(f'<line x1="{x:.1f}" y1="{T}" x2="{x:.1f}" y2="{T+PH}" stroke="{GRID}" stroke-width="1"/>')
        s.append(f'<text x="{x:.1f}" y="{T+PH+20}" font-size="11.5" text-anchor="middle" '
                 f'fill="{INK3}">{w}</text>')
    s.append(f'<text x="18" y="{T+PH/2:.1f}" font-size="12.5" text-anchor="middle" fill="{INK2}" '
             f'transform="rotate(-90 18 {T+PH/2:.1f})">advantage over reference  A_J</text>')
    s.append(f'<line x1="{L}" y1="{T}" x2="{L}" y2="{T+PH}" stroke="{INK3}" stroke-width="1"/>')

    # legend
    lx, ly = L + 2, T - 14
    s.append(f'<line x1="{lx}" y1="{ly}" x2="{lx+26}" y2="{ly}" stroke="{S1}" stroke-width="2"/>')
    s.append(f'<circle cx="{lx+13}" cy="{ly}" r="4.5" fill="{S1}" stroke="{SURFACE}" stroke-width="2"/>')
    s.append(f'<text x="{lx+33}" y="{ly+4}" font-size="12" fill="{INK}">'
             'controlled gradient — identical text, only the cut changes (76-word excerpts)</text>')
    s.append(f'<circle cx="{lx+476}" cy="{ly}" r="4.5" fill="{S2}" stroke="{SURFACE}" stroke-width="2"/>')
    s.append(f'<text x="{lx+488}" y="{ly+4}" font-size="12" fill="{INK}">'
             'main grid — strategy × granularity (478-word documents)</text>')

    # gradient line + markers
    pts = " ".join(f"{px(g['mean']):.1f},{py(g['A_J']):.1f}" for g in grad)
    s.append(f'<polyline points="{pts}" fill="none" stroke="{S1}" stroke-width="2" '
             f'stroke-linejoin="round"/>')
    for g in grad:
        x, y = px(g["mean"]), py(g["A_J"])
        s.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="5" fill="{S1}" '
                 f'stroke="{SURFACE}" stroke-width="2"/>')
        s.append(f'<text x="{x:.1f}" y="{y-13:.1f}" font-size="11.5" font-weight="600" '
                 f'text-anchor="middle" fill="{INK}">{esc(g["label"])}</text>')
        s.append(f'<text x="{x:.1f}" y="{y+22:.1f}" font-size="10.5" text-anchor="middle" '
                 f'fill="{INK3}">{g["mean"]:.2f}w</text>')

    # grid markers. Labels are placed greedily against an occupancy list so the
    # dense 15-21 word cluster stays legible: try right then left at the point's
    # own height, then step away vertically. First non-overlapping slot inside
    # the plot wins.
    CHW, LH = 6.0, 12.0                      # char width and line height at 11px
    # Seed the occupancy list with the gradient's own labels, so a grid label
    # cannot be placed underneath one of them (this is what put "headline" under
    # "sentence" before).
    boxes = []                               # placed label boxes, (x0,y0,x1,y1)
    for g in grad:
        gx, gy = px(g["mean"]), py(g["A_J"])
        hw = len(g["label"]) * 6.3 / 2 + 3
        boxes.append((gx - hw, gy - 23, gx + hw, gy - 9))          # the bold name
        sw = len(f'{g["mean"]:.2f}w') * 5.8 / 2 + 3
        boxes.append((gx - sw, gy + 13, gx + sw, gy + 25))         # the "3.92w" line

    def free(b):
        if b[0] < L + 2 or b[2] > L + PW - 2:
            return False
        return not any(b[0] < o[2] and o[0] < b[2] and b[1] < o[3] and o[1] < b[3]
                       for o in boxes)

    for c in sorted(grid, key=lambda c: -c["A_J"]):
        x, y = px(c["words"]), py(c["A_J"])
        s.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="5" fill="{S2}" '
                 f'stroke="{SURFACE}" stroke-width="2"/>')
        lbl = ("headline" if c["cell"].endswith("(full length)")
               else f'{SHORT[c["strategy"]]}·{GRAN[c["granularity"]]}')
        w = len(lbl) * CHW
        chosen = None
        for dy in (0, -LH, LH, -2 * LH, 2 * LH, -3 * LH, 3 * LH):
            for anchor, dx in (("start", 10), ("end", -10)):
                x0 = x + dx if anchor == "start" else x + dx - w
                box = (x0 - 2, y + dy - 7, x0 + w + 2, y + dy + 5)
                if free(box):
                    chosen = (anchor, dx, dy, box)
                    break
            if chosen:
                break
        anchor, dx, dy, box = chosen or ("start", 10, 0, (x + 8, y - 7, x + 10 + w, y + 5))
        boxes.append(box)
        s.append(f'<text x="{x+dx:.1f}" y="{y+dy+4:.1f}" font-size="11" text-anchor="{anchor}" '
                 f'fill="{INK2}">{esc(lbl)}</text>')

    # ── panel 2: how much contiguous original text the attacker ends up holding ──
    rec = json.load(open(os.path.join("results", "gradient", "recovery.json"),
                         encoding="utf-8"))
    order = [g["label"] for g in grad]
    xs = [px(g["mean"]) for g in grad]
    rv = [rec[k]["recovered_pct"] for k in order]
    fl = [rec[k]["floor_pct"] for k in order]

    s.append(f'<text x="{L}" y="{T2-44}" font-size="14" font-weight="600" fill="{INK}">'
             'How much of the 76-word document comes back as one contiguous stretch</text>')
    s.append(f'<text x="{L}" y="{T2-26}" font-size="12" fill="{INK2}">'
             'Controlled gradient only — the grid is not plotted here, because its documents are a '
             'different length. Longest run of fragments the</text>')
    s.append(f'<text x="{L}" y="{T2-11}" font-size="12" fill="{INK2}">'
             'attacker placed consecutively AND in true order, measured in words.</text>')

    for v in (0, 10, 20, 30, 40, 50, 60, 70):
        y = py2(v)
        s.append(f'<line x1="{L}" y1="{y:.1f}" x2="{L+PW}" y2="{y:.1f}" stroke="{GRID}" stroke-width="1"/>')
        s.append(f'<text x="{L-9}" y="{y+4:.1f}" font-size="11.5" text-anchor="end" '
                 f'fill="{INK3}">{v}%</text>')
    for w in (1, 2, 3, 4, 6, 10, 15, 20):
        x = px(w)
        s.append(f'<line x1="{x:.1f}" y1="{T2}" x2="{x:.1f}" y2="{T2+PH2}" stroke="{GRID}" stroke-width="1"/>')
        s.append(f'<text x="{x:.1f}" y="{T2+PH2+20}" font-size="11.5" text-anchor="middle" '
                 f'fill="{INK3}">{w}</text>')
    s.append(f'<line x1="{L}" y1="{T2}" x2="{L}" y2="{T2+PH2}" stroke="{INK3}" stroke-width="1"/>')
    s.append(f'<text x="{L+PW/2:.1f}" y="{T2+PH2+42}" font-size="12.5" text-anchor="middle" '
             f'fill="{INK2}">mean fragment length (words, log scale)</text>')
    s.append(f'<text x="18" y="{T2+PH2/2:.1f}" font-size="12.5" text-anchor="middle" fill="{INK2}" '
             f'transform="rotate(-90 18 {T2+PH2/2:.1f})">% of document recovered</text>')

    # the band between floor and recovered IS the attacker's contribution
    band = (" ".join(f"{x:.1f},{py2(v):.1f}" for x, v in zip(xs, rv)) + " " +
            " ".join(f"{x:.1f},{py2(v):.1f}" for x, v in reversed(list(zip(xs, fl)))))
    s.append(f'<polygon points="{band}" fill="{S1}" fill-opacity="0.13"/>')
    s.append(f'<polyline points="{" ".join(f"{x:.1f},{py2(v):.1f}" for x, v in zip(xs, fl))}" '
             f'fill="none" stroke="{INK3}" stroke-width="1.8" stroke-dasharray="5 4"/>')
    s.append(f'<polyline points="{" ".join(f"{x:.1f},{py2(v):.1f}" for x, v in zip(xs, rv))}" '
             f'fill="none" stroke="{S1}" stroke-width="2" stroke-linejoin="round"/>')
    for x, v, f_, lab in zip(xs, rv, fl, order):
        s.append(f'<circle cx="{x:.1f}" cy="{py2(v):.1f}" r="5" fill="{S1}" '
                 f'stroke="{SURFACE}" stroke-width="2"/>')
        s.append(f'<circle cx="{x:.1f}" cy="{py2(f_):.1f}" r="3.5" fill="{INK3}" '
                 f'stroke="{SURFACE}" stroke-width="2"/>')
        s.append(f'<text x="{x:.1f}" y="{py2(v)-13:.1f}" font-size="11.5" font-weight="600" '
                 f'text-anchor="middle" fill="{INK}">{v:.0f}%</text>')
    # Both annotations go in the empty gaps between plotted widths: the band's
    # interior at ~5.5 words, and the clear space under the dashed floor at ~13.
    s.append(f'<text x="{px(5.5):.1f}" y="{py2(24):.1f}" font-size="11" '
             f'text-anchor="middle" fill="{S1}">attacker’s contribution</text>')
    s.append(f'<text x="{px(13):.1f}" y="{py2(15):.1f}" font-size="11" '
             f'text-anchor="middle" fill="{INK2}">leaked by the cut alone '
             f'(longest single fragment)</text>')

    s.append(f'<text x="{L}" y="{H-20}" font-size="10.5" fill="{INK3}">'
             'Grid documents average 478 words (659 headline) against 76 for the excerpt arms, so the '
             'families differ in pool size and in</text>')
    s.append(f'<text x="{L}" y="{H-7}" font-size="10.5" fill="{INK3}">'
             'per-document context. Do not fit one curve through both.</text>')
    s.append("</svg>")

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    open(OUT, "w", encoding="utf-8").write("\n".join(s))
    print(f"wrote {OUT}")

    print("\nCONTROLLED GRADIENT (identical text, 76-word excerpts)")
    print(f"{'arm':10s} {'frags':>6s} {'w/frag':>7s} {'med':>4s} {'sd':>5s} {'min':>4s} {'max':>4s} "
          f"{'frags/doc':>9s} {'A_J':>8s}")
    for g in grad:
        print(f"{g['label']:10s} {g['n']:6d} {g['mean']:7.2f} {g['median']:4.1f} {g['sd']:5.2f} "
              f"{g['min']:4d} {g['max']:4d} {g['frags_per_doc']:9.2f} {g['A_J']:+8.4f}")

    print("\nMAIN GRID (478-word documents; headline 659)")
    print(f"{'cell':34s} {'gran':12s} {'w/frag':>7s} {'med':>6s} {'frags/doc':>9s} {'A_J':>8s}")
    for c in sorted(grid, key=lambda c: -c["words"]):
        print(f"{c['cell']:34s} {c['granularity']:12s} {c['words']:7.2f} {c['median']:6.2f} "
              f"{c['frags_per_doc']:9.2f} {c['A_J']:+8.4f}")

    print("\nBY GRANULARITY LABEL (grid only, mean over cells' per-unit means)")
    for g in sorted({c["granularity"] for c in grid}):
        cs = [c for c in grid if c["granularity"] == g]
        lo, hi = min(c["words"] for c in cs), max(c["words"] for c in cs)
        alo, ahi = min(c["A_J"] for c in cs), max(c["A_J"] for c in cs)
        print(f"  {g:13s} cells={len(cs)}  words/frag {st.fmean([c['words'] for c in cs]):5.2f} "
              f"(range {lo:5.2f}-{hi:5.2f})  A_J range {alo:+.4f} to {ahi:+.4f}")


if __name__ == "__main__":
    main()
