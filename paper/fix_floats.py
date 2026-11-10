"""
fix_floats.py — set each figure's float type from the figure's OWN native
width, and stop overriding the width.

The package figures are built at acmart's real dimensions: 239pt (one column)
for all but fig3_linkage_vs_ordering, which is 504pt (full text width). A
239pt figure placed in a figure* with width=\\textwidth is scaled 2.1x, which
magnifies 7-8pt type to about 16pt. Dropping the width option renders each
figure at its designed size, so the type matches the body text.

    python paper/fix_floats.py
"""

import io
import os
import re
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
TEX = os.path.join(HERE, "main.tex")
FIGDIR = os.path.join(HERE, "..", "results", "paper_package", "figures")
FULL_WIDTH_PT = 400.0          # anything wider than this is a two-column figure


def native_width(name):
    out = subprocess.run(["pdfinfo", os.path.join(FIGDIR, name)],
                         capture_output=True, text=True).stdout
    m = re.search(r"Page size:\s*([0-9.]+)\s*x", out)
    return float(m.group(1)) if m else None


def main():
    s = io.open(TEX, encoding="utf-8").read()
    block = re.compile(r"\\begin\{figure\*?\}(\[[^\]]*\])?(.*?)\\end\{figure\*?\}",
                       re.DOTALL)
    report = []

    def fix(m):
        placement, body = m.group(1) or "[t]", m.group(2)
        fn = re.search(r"\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}", body)
        if not fn:
            return m.group(0)
        name = fn.group(1)
        w = native_width(name)
        if w is None:
            return m.group(0)
        star = "*" if w > FULL_WIDTH_PT else ""
        # render at the figure's own size: no width override
        body = re.sub(r"(\\includegraphics)(?:\[[^\]]*\])?(\{)", r"\1\2", body)
        report.append((name, w, "figure*" if star else "figure"))
        return (f"\\begin{{figure{star}}}{placement}{body}"
                f"\\end{{figure{star}}}")

    s2 = block.sub(fix, s)
    io.open(TEX, "w", encoding="utf-8").write(s2)

    print(f"{'figure':34s} {'native w':>9s}  float")
    for name, w, kind in report:
        print(f"{name:34s} {w:8.0f}pt  {kind}")
    print(f"\n{len(report)} figures normalised")


if __name__ == "__main__":
    main()
