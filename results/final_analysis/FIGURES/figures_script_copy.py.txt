"""
figures.py — the paper figures (results plan §21, §27) from figure_data/*.csv.

Every figure is a PGFPlots picture that READS its CSV; the same picture is
compiled to the vector PDF, rasterised to the PNG preview and converted to SVG,
so the PNG, the vector file and the LaTeX all come from one dataset and no
plotted number is typed anywhere. For each figure N:
    FIGURES/figN_body.tex     the tikzpicture (reads \figdatadir/<csv>)
    FIGURES/figN.tex          standalone wrapper -> figN.pdf, figN.png, figN.svg
    FIGURES/figN_figure.tex   a manuscript figure environment (\input of the body)
    FIGURES/figN_graphic.tex  the same figure via \includegraphics of the PDF
Compiled with MiKTeX pdflatex with the package installer disabled.

    python results/final_analysis/scripts/figures.py
"""

import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.dirname(HERE)
ROOT = os.path.dirname(os.path.dirname(PKG))
FIG = os.path.join(PKG, "FIGURES")
sys.path.insert(0, os.path.join(ROOT, "analysis"))

from cost_model_v2 import MODEL_MAX_OUTPUT                     # noqa: E402

PREAMBLE = r"""\usepackage{pgfplots}
\usepackage{pgfplotstable}
\usepgfplotslibrary{groupplots}
\pgfplotsset{compat=1.16,
  every axis/.append style={font=\footnotesize, label style={font=\footnotesize},
    tick label style={font=\scriptsize}, legend style={font=\scriptsize, draw=none, fill=none}},
  discard if not/.style 2 args={x filter/.append code={%
    \edef\tempa{\thisrow{#1}}\edef\tempb{#2}\ifx\tempa\tempb\else\def\pgfmathresult{inf}\fi}},
  cls/.style={scatter, only marks, scatter src=explicit symbolic, mark size=1.1pt,
    scatter/classes={headline={mark=*,black,fill opacity=0.5,draw opacity=0.5},
      sentence={mark=o,blue!70!black}, clause={mark=square,red!70!black},
      token-window={mark=triangle,green!45!black}, grid={mark=o,gray},
      identifier={mark=diamond,orange!80!black}, rbnc={mark=x,red,mark size=3pt,thick}}}}
"""

FIGS = {}


def fig(n, caption):
    def deco(fn):
        FIGS[n] = (fn, caption)
        return fn
    return deco


def tbl(name, macro):
    return rf"\pgfplotstableread[col sep=comma]{{\figdatadir/{name}.csv}}{macro}" + "\n"


@fig(1, "Headline game J: raw ordered-pair F1\\textsubscript{J} by attacker (points: pools; bars: mean with 95\\% "
        "percentile-bootstrap CI over pools). $\\dagger$\\,Post-hoc exploratory attacker (RUN\\_DECISIONS D14): "
        "motivated by the observed Memon-inspired\\,/\\,Sonnet gap, frozen before its own evaluation. The "
        "hierarchical attacker is pending.")
def f1():
    return tbl("fig1_summary", r"\sumt") + tbl("fig1_pools", r"\poolt") + r"""
\begin{tikzpicture}
\begin{axis}[width=10cm, height=6cm, ymin=0, ymax=1, xmin=-0.6, xmax=4.6,
  xtick={0,1,2,3,4}, xticklabels={Analytic one-bucket, Memon-inspired, Embedding$^{\dagger}$ (post hoc), One-shot Sonnet, Hierarchical},
  x tick label style={align=center, text width=1.9cm}, ylabel={F1$_J$}, ymajorgrids, grid style={gray!20}]
\addplot[only marks, mark=*, mark size=0.8pt, gray!60] table[x=x, y=F1_J] {\poolt};
\addplot[only marks, mark=square*, mark size=2.2pt, black, error bars/.cd, y dir=both, y explicit,
  error bar style={thick}] table[x=idx, y=mean, y error plus=errhi, y error minus=errlo] {\sumt};
\node[font=\scriptsize, gray, align=center] at (axis cs:4,0.5) {pending\\(not run)};
\end{axis}
\end{tikzpicture}"""


@fig(2, "Grid game J across all nine retained cells (24 pools each; one-shot random\\,/\\,token-window: 23 "
        "completed). Mean F1\\textsubscript{J} with 95\\% bootstrap CIs; dashes: analytic baseline. "
        "$\\dagger$\\,Post-hoc exploratory attacker (D14); its primary comparison is F1\\textsubscript{L} (Figure 3).")
def f2():
    return tbl("fig2_grid_J", r"\gt") + r"""
\begin{tikzpicture}
\begin{axis}[width=12cm, height=6.2cm, ymin=0, ymax=1, xmin=-0.6, xmax=8.6, xtick=data,
  xticklabels from table={\gt}{cell}, x tick label style={rotate=35, anchor=east},
  ylabel={F1$_J$}, ymajorgrids, grid style={gray!20}, legend cell align=left, legend columns=3,
  legend style={at={(0.5,1.02)}, anchor=south}]
\addplot[only marks, mark=*, mark size=2pt, blue!70!black, error bars/.cd, y dir=both, y explicit]
  table[x=idx, y=sonnet, y error plus=sonnet_errhi, y error minus=sonnet_errlo] {\gt};
\addlegendentry{One-shot Sonnet}
\addplot[only marks, mark=triangle*, mark size=2pt, orange!80!black, error bars/.cd, y dir=both, y explicit]
  table[x expr=\thisrow{idx}+0.22, y=memon, y error plus=memon_errhi, y error minus=memon_errlo] {\gt};
\addlegendentry{Memon-inspired}
\addplot[only marks, mark=diamond*, mark size=2.2pt, green!45!black, error bars/.cd, y dir=both, y explicit]
  table[x expr=\thisrow{idx}-0.22, y=emb, y error plus=emb_errhi, y error minus=emb_errlo] {\gt};
\addlegendentry{Embedding$^{\dagger}$ (post hoc)}
\addplot[only marks, mark=-, mark size=5pt, thick, gray] table[x=idx, y=baseline] {\gt};
\addlegendentry{analytic baseline}
\draw[gray!50, dashed] (axis cs:2.5,0) -- (axis cs:2.5,1);
\draw[gray!50, dashed] (axis cs:6.5,0) -- (axis cs:6.5,1);
\end{axis}
\end{tikzpicture}"""


@fig(3, "Linkage vs ordering decomposition: linkage component F1\\textsubscript{L} (mean, 95\\% CI) against "
        "micro-averaged direction accuracy q (95\\% CI), by condition. F1\\textsubscript{J} = F1\\textsubscript{L} "
        "$\\times$ q. Dotted line: q = 0.5 (chance direction). Labels: rnd = random, sem = semantic, coh = "
        "coherence-sever, sv = subject-verb; sent = sentence, cl = clause, tw = token-window. $\\dagger$\\,Post-hoc "
        "exploratory embedding attacker (D14): read it along the x-axis, F1\\textsubscript{L} being its primary "
        "comparison.")
def f3():
    return tbl("fig3_decomposition", r"\dt") + r"""
\begin{tikzpicture}
\begin{axis}[width=9cm, height=7cm, xmin=0, xmax=1, ymin=0.3, ymax=1, xlabel={linkage F1$_L$},
  ylabel={direction accuracy $q_{\mathrm{micro}}$}, grid=major, grid style={gray!20},
  legend pos=south east, legend cell align=left]
\addplot[only marks, mark=*, mark size=1.8pt, blue!70!black, restrict expr to domain={\thisrow{sid}}{0:0},
  nodes near coords, point meta=explicit symbolic, every node near coord/.style={font=\tiny, anchor=west, gray!80!black},
  error bars/.cd, x dir=both, x explicit, y dir=both, y explicit]
  table[x=F1_L, y=q_micro, meta=short, x error plus=F1_L_errhi, x error minus=F1_L_errlo,
        y error plus=q_errhi, y error minus=q_errlo] {\dt};
\addlegendentry{One-shot Sonnet}
\addplot[only marks, mark=triangle*, mark size=1.8pt, orange!80!black, restrict expr to domain={\thisrow{sid}}{1:1},
  error bars/.cd, x dir=both, x explicit, y dir=both, y explicit]
  table[x=F1_L, y=q_micro, x error plus=F1_L_errhi, x error minus=F1_L_errlo,
        y error plus=q_errhi, y error minus=q_errlo] {\dt};
\addlegendentry{Memon-inspired}
\addplot[only marks, mark=diamond*, mark size=2pt, green!45!black, restrict expr to domain={\thisrow{sid}}{2:2},
  error bars/.cd, x dir=both, x explicit, y dir=both, y explicit]
  table[x=F1_L, y=q_micro, x error plus=F1_L_errhi, x error minus=F1_L_errlo,
        y error plus=q_errhi, y error minus=q_errlo] {\dt};
\addlegendentry{Embedding$^{\dagger}$ (post hoc)}
\draw[dotted, gray] (axis cs:0,0.5) -- (axis cs:1,0.5);
\end{axis}
\end{tikzpicture}"""


@fig(4, "Game O (membership given): Kendall $\\tau$ by condition, mean with 95\\% bootstrap CI over documents "
        "(headline: 100 documents; each grid cell: the same 30). Solid line: Random ($\\tau$ = 0).")
def f4():
    return tbl("fig4_grid_O", r"\ot") + r"""
\begin{tikzpicture}
\begin{axis}[width=12cm, height=6.2cm, ymin=-0.25, ymax=1, xmin=-0.6, xmax=9.6, xtick=data,
  xticklabels from table={\ot}{condition}, x tick label style={rotate=35, anchor=east},
  ylabel={Kendall $\tau$}, ymajorgrids, grid style={gray!20}, legend cell align=left,
  legend columns=3, legend style={at={(0.5,1.02)}, anchor=south}]
\addplot[only marks, mark=*, mark size=2pt, blue!70!black, error bars/.cd, y dir=both, y explicit]
  table[x=idx, y=sonnet, y error plus=sonnet_errhi, y error minus=sonnet_errlo] {\ot};
\addlegendentry{One-shot Sonnet}
\addplot[only marks, mark=square*, mark size=1.6pt, gray, error bars/.cd, y dir=both, y explicit]
  table[x expr=\thisrow{idx}+0.2, y=greedy, y error plus=greedy_errhi, y error minus=greedy_errlo] {\ot};
\addlegendentry{Jaccard-Greedy}
\addplot[only marks, mark=diamond*, mark size=1.8pt, gray!60!black, error bars/.cd, y dir=both, y explicit]
  table[x expr=\thisrow{idx}+0.4, y=mst, y error plus=mst_errhi, y error minus=mst_errlo] {\ot};
\addlegendentry{Jaccard-MST}
\draw[black] (axis cs:-0.6,0) -- (axis cs:9.6,0);
\draw[gray!50, dashed] (axis cs:0.5,-0.25) -- (axis cs:0.5,1);
\end{axis}
\end{tikzpicture}"""


@fig(5, "Identifier game J (20 pools). (a) F1\\textsubscript{J}, mean with 95\\% CI; dashed: analytic baseline, "
        "dotted: schema-aware baseline. (b) Normalized advantage over the schema-aware baseline with its frozen "
        "90\\% CI; shaded: the frozen $\\pm$0.10 near-baseline band.")
def f5():
    return tbl("fig5a_identifier", r"\ia") + tbl("fig5b_identifier_rule", r"\ib") + \
        tbl("fig5c_constants", r"\ic") + r"""
\pgfplotstablegetelem{0}{value}\of\ic \let\analyticb\pgfplotsretval
\pgfplotstablegetelem{1}{value}\of\ic \let\schemab\pgfplotsretval
\pgfplotstablegetelem{2}{value}\of\ic \let\margin\pgfplotsretval
\begin{tikzpicture}
\begin{groupplot}[group style={group size=2 by 1, horizontal sep=1.6cm}, width=7cm, height=5.6cm,
  xmin=-0.6, xmax=3.6, xtick={0,1,2,3}, x tick label style={align=center, text width=1.5cm}, ymajorgrids,
  grid style={gray!20}]
\nextgroupplot[ymin=0, ymax=0.35, ylabel={F1$_J$}, xticklabels from table={\ia}{attacker}, title={(a)}]
\addplot[only marks, mark=square*, mark size=2pt, black, error bars/.cd, y dir=both, y explicit]
  table[x=idx, y=mean, y error plus=errhi, y error minus=errlo] {\ia};
\addplot[dashed, gray, domain=-0.6:3.6] {\analyticb};
\addplot[dotted, thick, gray!70!black, domain=-0.6:3.6] {\schemab};
\nextgroupplot[ymin=-0.4, ymax=0.2, ylabel={$A_{\mathrm{schema}}$}, xticklabels from table={\ib}{attacker},
  title={(b)}]
\fill[green!15] (axis cs:-0.6,-\margin) rectangle (axis cs:3.6,\margin);
\addplot[only marks, mark=square*, mark size=2pt, black, error bars/.cd, y dir=both, y explicit]
  table[x=idx, y=mean, y error plus=errhi, y error minus=errlo] {\ib};
\draw[gray] (axis cs:-0.6,0) -- (axis cs:3.6,0);
\end{groupplot}
\end{tikzpicture}"""


def scatter_pair(a, b, xa, xb, ya, yb):
    return tbl(a, r"\sa") + tbl(b, r"\sb") + rf"""
\begin{{tikzpicture}}
\begin{{groupplot}}[group style={{group size=2 by 1, horizontal sep=1.6cm}}, width=6.6cm, height=5.6cm,
  grid=major, grid style={{gray!20}}]
\nextgroupplot[xlabel={{{xa}}}, ylabel={{{ya}}}, ymin=0, ymax=1, title={{(a) game J, one-shot Sonnet, pools}},
  legend to name=leg, legend columns=4]
\addplot[cls] table[x=x, y=y, meta=cls] {{\sa}};
\legend{{headline, sentence, clause, token-window}}
\nextgroupplot[xlabel={{{xb}}}, ylabel={{{yb}}}, ymin=-0.3, ymax=1, title={{(b) game O, one-shot Sonnet, documents}}]
\addplot[cls] table[x=x, y=y, meta=cls] {{\sb}};
\end{{groupplot}}
\node[anchor=north] at ($(group c1r1.south)!0.5!(group c2r1.south)+(0,-0.9cm)$) {{\ref{{leg}}}};
\end{{tikzpicture}}"""


@fig(6, "Document length vs reconstruction. (a) Pool mean source-document length (words) vs F1\\textsubscript{J}; "
        "(b) document length vs Kendall $\\tau$. Association only; Spearman $\\rho$ with CIs in Table R.")
def f6():
    return scatter_pair("fig6a_length_J", "fig6b_length_O", "mean document length (words)",
                        "document length (words)", "F1$_J$", "Kendall $\\tau$")


@fig(7, "Fragment count vs reconstruction. (a) Fragments per pool vs F1\\textsubscript{J}; (b) fragments per "
        "document vs Kendall $\\tau$.")
def f7():
    return scatter_pair("fig7a_count_J", "fig7b_count_O", "fragments per pool", "fragments per document",
                        "F1$_J$", "Kendall $\\tau$")


@fig(8, "Fragment size vs reconstruction. (a) Mean fragment length (words) in the pool vs F1\\textsubscript{J}; "
        "(b) mean fragment length in the document vs Kendall $\\tau$.")
def f8():
    return scatter_pair("fig8a_size_J", "fig8b_size_O", "mean fragment length (words)",
                        "mean fragment length (words)", "F1$_J$", "Kendall $\\tau$")


@fig(10, "Resource scaling for one-shot Sonnet in game J: fragments per pool vs billed output tokens of the "
         "answering call (mostly reasoning; repair calls excluded). Dashed line: the 128k per-call budget; cross: "
         "the one resource-bounded non-completion.")
def f10():
    return tbl("fig10_resource", r"\rt") + tbl("fig10_cap", r"\capt") + r"""
\pgfplotstablegetelem{0}{value}\of\capt \let\cap\pgfplotsretval
\begin{tikzpicture}
\begin{axis}[width=9cm, height=6cm, xlabel={fragments per pool}, ylabel={output tokens (answering call)},
  grid=major, grid style={gray!20}, ymin=0, legend pos=south east, legend cell align=left,
  scaled y ticks=base 10:-3, ytick scale label code/.code={}, yticklabel={\pgfmathprintnumber{\tick}k}]
\addplot[scatter, only marks, scatter src=explicit symbolic, mark size=1.2pt,
  scatter/classes={headline={mark=*,black,fill opacity=0.5,draw opacity=0.5}, grid={mark=o,gray},
    identifier={mark=diamond,orange!80!black}, rbnc={mark=x,red,mark size=3.5pt,thick}}]
  table[x=x, y=y, meta=cls] {\rt};
\legend{headline, grid, identifier, RBNC (128k)}
\addplot[dashed, red!60!black, domain=0:560] {\cap};
\end{axis}
\end{tikzpicture}"""


def compile_one(n):
    fn, caption = FIGS[n]
    body = fn()
    open(os.path.join(FIG, f"fig{n}_body.tex"), "w", encoding="utf-8").write(
        f"% generated by results/final_analysis/scripts/figures.py; data: figure_data/\n{body}\n")
    open(os.path.join(FIG, f"fig{n}.tex"), "w", encoding="utf-8").write(
        "\\documentclass[border=4pt]{standalone}\n" + PREAMBLE + "\\usetikzlibrary{calc}\n"
        "\\providecommand{\\figdatadir}{../figure_data}\n\\begin{document}\n"
        f"\\input{{fig{n}_body.tex}}\n\\end{{document}}\n")
    open(os.path.join(FIG, f"fig{n}_figure.tex"), "w", encoding="utf-8").write(
        "% Manuscript: needs \\usepackage{pgfplots}, \\usepgfplotslibrary{groupplots}, \\usetikzlibrary{calc}\n"
        "% and the pgfplotsset block from figures.py PREAMBLE; set \\figdatadir to the figure_data directory.\n"
        "\\begin{figure}[t]\\centering\n"
        f"\\input{{fig{n}_body.tex}}\n\\caption{{{caption}}}\n\\label{{fig:{n}}}\n\\end{{figure}}\n")
    open(os.path.join(FIG, f"fig{n}_graphic.tex"), "w", encoding="utf-8").write(
        "\\begin{figure}[t]\\centering\n"
        f"\\includegraphics[width=\\linewidth]{{FIGURES/fig{n}.pdf}}\n\\caption{{{caption}}}\n"
        f"\\label{{fig:{n}}}\n\\end{{figure}}\n")
    for _pass in (1, 2):                      # two passes: legend-to-name references resolve on the second
        r = subprocess.run(["pdflatex", "-interaction=nonstopmode", "-halt-on-error", "--disable-installer",
                            f"fig{n}.tex"], cwd=FIG, capture_output=True, text=True, errors="replace")
        if r.returncode != 0:
            break
    pdf = os.path.join(FIG, f"fig{n}.pdf")
    if r.returncode != 0 or not os.path.exists(pdf):
        err = [l for l in r.stdout.splitlines() if l.startswith("!") or "Error" in l][:6]
        print(f"fig{n}: FAILED\n   " + "\n   ".join(err))
        return False
    subprocess.run(["pdftoppm", "-png", "-r", "220", "-singlefile", f"fig{n}.pdf", f"fig{n}"], cwd=FIG)
    subprocess.run(["pdftocairo", "-svg", f"fig{n}.pdf", f"fig{n}.svg"], cwd=FIG)
    for ext in (".aux", ".log"):
        p = os.path.join(FIG, f"fig{n}{ext}")
        if os.path.exists(p):
            os.remove(p)
    print(f"fig{n}: pdf, png, svg")
    return True


def main():
    os.makedirs(FIG, exist_ok=True)
    fd = os.path.join(PKG, "figure_data")
    # constants the figures draw, written as data so no number is typed into LaTeX
    import csv
    import json
    rule = json.load(open(os.path.join(PKG, "KEY_NUMBERS.json"), encoding="utf-8"))
    with open(os.path.join(fd, "fig5c_constants.csv"), "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["name", "value"])
        w.writerow(["analytic_baseline", rule["identifier"]["Analytic one-bucket"]["F1_J_mean"]])
        w.writerow(["schema_baseline", rule["identifier"]["Schema-order"]["F1_J_mean"]])
        w.writerow(["near_baseline_margin", 0.10])          # the frozen D11 margin
    with open(os.path.join(fd, "fig10_cap.csv"), "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["name", "value"])
        w.writerow(["max_output_tokens", MODEL_MAX_OUTPUT])
    shutil.copy(__file__, os.path.join(FIG, "figures_script_copy.py.txt"))
    ok = [compile_one(n) for n in sorted(FIGS)]
    print(f"{sum(ok)}/{len(ok)} figures compiled into {FIG}")


if __name__ == "__main__":
    main()
