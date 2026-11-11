r"""
Where did each exhibit land, relative to the section that discusses it?

    python tools/page_map.py paper/main.tex paper/main.pdf [--brief]

A spanning float cannot print on the page it is declared on, so the exhibits
are deliberately declared about a page BEFORE their section in main.tex. That
means the source position says nothing about where an exhibit belongs; HOME
below does. An exhibit more than one page either side of its home section is
flagged: nobody should turn two pages to find the evidence for a claim.
"""
import io
import os
import re
import subprocess
import sys

tex, pdf = sys.argv[1], sys.argv[2]
brief = "--brief" in sys.argv
src = io.open(tex, encoding="utf-8").read()
tabdir = os.path.join(os.path.dirname(os.path.abspath(tex)), "..", "results",
                      "paper_package", "tables")

# exhibit -> the subsection that discusses it
HOME = [
    ("table2_headline_attackers", "A generative attacker operates in a different regime"),
    ("table9_adjacency",          "A generative attacker operates in a different regime"),
    ("table3_grid",               "Fragmentation strategy and granularity"),
    ("fig3_linkage_vs_ordering",  "Linkage versus ordering"),
    ("table4_gameO",              "Ordering when membership is given"),
    ("table5_identifiers",        "Structured identifiers"),
    ("fig6_granularity_gradient", "A controlled granularity series"),
    ("table8_gradient",           "A controlled granularity series"),
    ("table6_single_token",       "A controlled granularity series"),
]


def norm(t):
    t = re.sub(r"\$[^$]*\$", " ", t)
    t = re.sub(r"\\[a-zA-Z@]+(\[[^\]]*\])?", " ", t)
    t = re.sub(r"[^a-z ]+", " ", t.lower())
    return re.sub(r"\s+", " ", t).strip()


npages = int([l for l in subprocess.run(["pdfinfo", pdf], capture_output=True,
                                        text=True).stdout.splitlines()
              if l.startswith("Pages")][0].split()[-1])
pages = {n: norm(subprocess.run(["pdftotext", "-f", str(n), "-l", str(n), pdf, "-"],
                                capture_output=True, text=True, encoding="utf-8",
                                errors="replace").stdout)
         for n in range(1, npages + 1)}


def where(text, nwords, start=1):
    probe = " ".join(norm(text).split()[:nwords])
    for n in range(start, npages + 1):
        if probe and probe in pages[n]:
            return n
    return None


def caption_of(name):
    if name.startswith("table"):
        t = io.open(os.path.join(tabdir, name + ".tex"), encoding="utf-8").read()
        return re.search(r"\\caption\{(.+?)\}\n", t, re.DOTALL).group(1)
    k = src.index(name)
    m = re.search(r"\\caption\{(.+?)\}\s*\\label", src[k:], re.DOTALL)
    return m.group(1)


# headings also appear in running text, so anchor on the first results page
start = where("A generative attacker operates in a different regime", 6) or 1
start = max(1, start - 1)

lags, rows = [], []
for name, home in HOME:
    if name not in src:
        continue                      # exhibit not in the paper
    hp = where(home, 5, start=start)
    ep = where(caption_of(name), 7, start=start)
    lag = (ep - hp) if (hp and ep) else None
    lags.append(lag)
    rows.append((name, home, hp, ep, lag))

worst = max((abs(l) for l in lags if l is not None), default=0)
far = sum(1 for l in lags if l is None or abs(l) > 1)
if brief:
    print("lags " + " ".join("?" if l is None else "%+d" % l for l in lags)
          + "  far=%d" % far)
else:
    for name, home, hp, ep, lag in rows:
        flag = "" if (lag is not None and abs(lag) <= 1) else "   <-- too far"
        print("  %-28s p%-3s section p%-3s %s%s"
              % (name, ep, hp, "?" if lag is None else "%+d" % lag, flag))
    print("  exhibits more than one page from their section: %d" % far)
sys.exit(1 if far else 0)
