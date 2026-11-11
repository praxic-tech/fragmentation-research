r"""
For every table: which page is the table on, and which page is each of its
notes on? Reads the note text straight out of the generated .tex rather than
guessing at markup, and searches the PDF page by page for a 10-word run.

Usage: check_attach.py <tables dir> <pdf>
"""
import glob
import io
import os
import re
import subprocess
import sys

tabdir, pdf = sys.argv[1], sys.argv[2]


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


def where(text, nwords=10):
    w = norm(text).split()
    if len(w) < nwords:
        return None
    probe = " ".join(w[:nwords])
    hits = [n for n in pages if probe in pages[n]]
    return hits[0] if len(hits) == 1 else (hits if hits else None)


bad = 0
for f in sorted(glob.glob(os.path.join(tabdir, "table*.tex"))):
    src = io.open(f, encoding="utf-8").read()
    name = os.path.basename(f)[:-4]
    cap = re.search(r"\\caption(?:of\{table\})?\{(.+?)\}\n", src, re.DOTALL).group(1)
    cap_page = where(cap)

    # notes are everything after the tabular box, one per source line
    body = src[src.index("usebox0"):]
    lines = [l for l in body.splitlines()
             if len(norm(l).split()) >= 12 and "includegraphics" not in l]
    note_pages = [where(l) for l in lines]
    note_pages = [p for p in note_pages if isinstance(p, int)]

    spread = sorted(set(note_pages))
    ok = spread in ([], [cap_page])
    if not ok:
        bad += 1
    print("  %-28s table p%-3s notes %s%s"
          % (name, cap_page, spread or "(none found)",
             "" if ok else "   <-- DETACHED"))

print("  detached: %d" % bad)
sys.exit(1 if bad else 0)
