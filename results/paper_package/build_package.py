"""
build_package.py — assemble the drop-in figure and table package. NO API CALLS.

Collects the final figures and tables into results/paper_package/ with a
manifest, and zips it. Copies only; it never regenerates, so the package can
never disagree with what the generators produced. Run the generators first:

    Rscript results/paper_figures_r/make_all.R      # figures + validation
    python  results/paper_tables/make_tables.py     # tables

    python  results/paper_package/build_package.py
"""

import hashlib
import json
import os
import shutil
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(ROOT)
PKG = "results/paper_package"
FIG_SRC = "results/paper_figures_r"
TAB_SRC = "results/paper_tables"

# (name, number, placement, width, status, one-line what it shows)
FIGURES = [
    ("fig1_headline_attackers", "1", "Main", "1 col", "Prespecified; embedding row post hoc",
     "The generative attacker reconstructs far more than the tested statistical and similarity attackers"),
    ("fig2_grid_reconstruction", "2", "Main", "1 col", "Prespecified",
     "Reconstruction across nine strategy x granularity cells"),
    ("fig3_linkage_vs_ordering", "3", "Main", "1 col", "Prespecified",
     "The joint score split into linkage and conditional ordering"),
    ("fig4_identifiers", "4", "Main", "1 col", "Prespecified; D11 baselines",
     "Structured identifiers behave qualitatively differently from prose"),
    ("fig5_single_token", "5", "Main", "1 col", "POST-HOC EXPLORATORY (D16)",
     "Single-token cuts drive null-adjusted joint reconstruction to about its random-shuffle reference"),
    ("fig6_granularity_gradient", "6", "Main", "1 col", "POST-HOC EXPLORATORY (D16, D18)",
     "Five cuts of identical text: observed against the random-shuffle reference, and what it means in words"),
    ("figA_gameO_vs_gameJ", "A", "Appendix", "1 col", "Prespecified",
     "Ordering with membership given is much easier than joint recovery"),
    ("figB_resource_scaling", "B", "Appendix", "1 col", "Prespecified; single-token points post hoc",
     "Output grows with fragment count, but fragment count does not determine completion"),
    ("figC_token_raw_vs_null", "C", "Appendix", "1 col", "POST-HOC EXPLORATORY (D16)",
     "What A_VJ near zero means in raw terms"),
]

TABLES = [
    ("table1_design", "1", "Prespecified", "The design: corpora, cells, pools, units"),
    ("table2_headline_attackers", "2", "Prespecified; embedding row post hoc",
     "Headline attacker comparison with 95% CIs"),
    ("table3_grid", "3", "Prespecified", "The nine-cell grid"),
    ("table4_gameO", "4", "Prespecified", "Game O: ordering with membership given"),
    ("table5_identifiers", "5", "Prespecified; D11 baselines", "The structured-identifier arm"),
    ("table6_single_token", "6", "POST-HOC EXPLORATORY (D16)",
     "Sentence against single-token cuts on identical excerpts, paired"),
    ("table7_resources", "7", "Prespecified", "Resources, completion and cost"),
    ("table8_gradient", "8", "POST-HOC EXPLORATORY (D16, D18)",
     "The five-point granularity gradient, with its random-shuffle reference per arm"),
    ("table9_adjacency", "9", "Post hoc, free reanalysis",
     "Precedence against adjacency, and a random attacker that is a legal answer"),
]


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for b in iter(lambda: fh.read(1 << 16), b""):
            h.update(b)
    return h.hexdigest()[:12]


def main():
    for sub in ("figures", "tables"):
        d = os.path.join(PKG, sub)
        shutil.rmtree(d, ignore_errors=True)
        os.makedirs(d)

    man, missing = {"figures": [], "tables": []}, []

    for name, num, place, width, status, what in FIGURES:
        row = {"figure": num, "name": name, "placement": place, "width": width,
               "status": status, "shows": what, "files": {}}
        for ext in (".pdf", ".png", ".svg", ".csv"):
            src = os.path.join(FIG_SRC, name + ext)
            if os.path.exists(src):
                shutil.copy2(src, os.path.join(PKG, "figures", name + ext))
                row["files"][ext[1:]] = sha(src)
            elif ext == ".pdf":
                missing.append(src)
        man["figures"].append(row)

    for name, num, status, what in TABLES:
        row = {"table": num, "name": name, "status": status, "shows": what, "files": {}}
        for ext in (".tex", ".md"):
            src = os.path.join(TAB_SRC, name + ext)
            if os.path.exists(src):
                shutil.copy2(src, os.path.join(PKG, "tables", name + ext))
                row["files"][ext[1:]] = sha(src)
            elif ext == ".tex":
                missing.append(src)
        man["tables"].append(row)

    if missing:
        raise SystemExit("STOP, these are missing -- run the generators first:\n  "
                         + "\n  ".join(missing))

    json.dump(man, open(os.path.join(PKG, "manifest.json"), "w", encoding="utf-8"), indent=1)
    write_readme(man)

    zp = os.path.join(PKG, "paper_package.zip")
    if os.path.exists(zp):
        os.remove(zp)
    with zipfile.ZipFile(zp, "w", zipfile.ZIP_DEFLATED) as z:
        for sub in ("figures", "tables"):
            for f in sorted(os.listdir(os.path.join(PKG, sub))):
                z.write(os.path.join(PKG, sub, f), f"{sub}/{f}")
        for f in ("README.md", "manifest.json"):
            z.write(os.path.join(PKG, f), f)
    print(f"\nwrote {zp} ({os.path.getsize(zp)/1024:.0f} KB)")
    print(f"  {len(man['figures'])} figures, {len(man['tables'])} tables")


def write_readme(man):
    L = ["# Figure and table package", "",
         "Drop-in figures and tables for the paper. **Copies only** — this directory is",
         "assembled by `build_package.py` from the generator outputs and is never edited",
         "by hand, so it cannot disagree with them.", "",
         "## Rebuild", "", "```bash",
         "Rscript results/paper_figures_r/make_all.R      # figures, then validation",
         "python  results/paper_tables/make_tables.py     # tables",
         "python  results/paper_package/build_package.py  # this package",
         "```", "",
         "`make_all.R` ends in `validate_figures.R`, which checks every figure's CSV",
         "against the frozen source artifacts independently of the plotting code and",
         "stops on any failure. No number in either directory is typed by hand.", "",
         "## Using these in the paper", "",
         "The paper is `acmart` with `\\documentclass[sigconf]{acmart}`. Figures are sized",
         "for a single column (3.33in = acmart sigconf's 241.14749pt) and set in Linux",
         "Biolinum, the template's own sans, at 8pt axis titles and 7pt ticks.", "",
         "```latex",
         "\\begin{figure}[t]",
         "  \\includegraphics{fig6_granularity_gradient.pdf}",
         "  \\caption{...}\\label{fig:gradient}",
         "\\end{figure}",
         "```", "",
         "Tables are `table*` environments that span both columns and carry their own",
         "caption, label and notes; `\\input{}` them directly. Each shrinks to",
         "`\\textwidth` only if it is wider than the page, and is never enlarged.", "",
         "**Text in the figure PDFs is outlines, not selectable text.** `pdffonts` lists",
         "no fonts at all, which satisfies any embedding requirement trivially, but the",
         "text cannot be selected, searched or read by a screen reader. This is a Windows",
         "limitation, not a choice: see the Fonts section of",
         "`results/paper_figures_r/README.md`. Rebuilding on Linux or macOS produces real",
         "embedded text with no other change.", "",
         "## Figures", "",
         "| # | File | Placement | Width | Status | Shows |",
         "|---|---|---|---|---|---|"]
    for r in man["figures"]:
        L.append(f"| {r['figure']} | `{r['name']}.pdf` | {r['placement']} | {r['width']} | "
                 f"{r['status']} | {r['shows']} |")
    L += ["", "Each figure ships `.pdf` (vector, for the paper), `.png` (600 dpi), `.svg`,",
          "and `.csv` holding exactly the data frame it was drawn from.", "",
          "## Tables", "", "| # | File | Status | Shows |", "|---|---|---|---|"]
    for r in man["tables"]:
        L.append(f"| {r['table']} | `{r['name']}.tex` | {r['status']} | {r['shows']} |")
    L += ["", "Each table ships `.tex` (booktabs, ready to `\\input`) and `.md` (the same",
          "content for review).", "",
          "## Reading the post-hoc material", "",
          "Figures 5 and 6 and Tables 6 and 8 are **post-hoc exploratory** (D16, D18) and",
          "are labelled as such in their own captions and notes. They were designed after",
          "results were seen; the claim restrictions in `docs/RUN_DECISIONS.md` carry over.",
          "Table 9 is a free reanalysis of predictions already on disk.", "",
          "## Two things to check before submitting", "",
          "- The granularity material rests on `A_VJ`, the visible-text metric D16 froze",
          "  as primary. Its random-shuffle reference is **not constant across arms** (it",
          "  falls from 0.423 at the sentence cut to 0.141 at one word), so raw `V_J` is",
          "  not comparable between arms and the normalised column is the one to read.",
          "- PoPETs 2027 caps the main body at 12 typeset pages and desk-rejects",
          "  over-length papers without appeal. Nine figures and nine tables will not all",
          "  fit; the appendix figures (A, B, C) and the wider tables are the first to cut.",
          "  Evaluations on purely synthetic data also require a well-marked paragraph",
          "  arguing the results extrapolate, which the identifier arm needs.", "",
          "`manifest.json` carries the same table plus a SHA-256 prefix for every file."]
    open(os.path.join(PKG, "README.md"), "w", encoding="utf-8").write("\n".join(L) + "\n")


if __name__ == "__main__":
    main()
