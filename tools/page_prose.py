r"""
Count lines of BODY PROSE per page, not ink.

Ink was the wrong measure: a table's notes are hundreds of words of 6pt text,
so a page can read as 93% full and still carry no argument at all. This takes
the running prose out of main.tex, fingerprints each paragraph, and reports
which page each one landed on. A page with no fingerprint on it is an
exhibit-only page.

Usage: prose.py <main.tex> <pdf>
"""
import io
import re
import subprocess
import sys

tex, pdf = sys.argv[1], sys.argv[2]
src = io.open(tex, encoding="utf-8").read()

# body only
src = src.split(r"\maketitle", 1)[-1]
src = src.split(r"\appendix", 1)[0]

# drop everything that is not running prose
src = re.sub(r"\\begin\{(figure\*?|table\*?|strip|center)\}.*?\\end\{\1\}", " ",
             src, flags=re.DOTALL)
src = re.sub(r"\\input\{[^}]*\}", " ", src)
src = re.sub(r"(?m)^%.*$", " ", src)


def norm(t):
    t = re.sub(r"\$[^$]*\$", " ", t)          # maths renders differently
    t = re.sub(r"\\[a-zA-Z@]+\s*", " ", t)
    t = re.sub(r"[^a-z ]+", " ", t.lower())
    return re.sub(r"\s+", " ", t).strip()


paras = [p for p in re.split(r"\n\s*\n", src) if len(norm(p).split()) >= 25]
prints = []
for p in paras:
    w = norm(p).split()
    # several windows: a paragraph counts as found if any of them matches
    prints.append([" ".join(w[i:i + 5]) for i in (1, 6, 11, 16) if len(w) > i + 5])

npages = int([l for l in subprocess.run(["pdfinfo", pdf], capture_output=True,
                                        text=True).stdout.splitlines()
              if l.startswith("Pages")][0].split()[-1])

pages = {}
for n in range(1, npages + 1):
    txt = subprocess.run(["pdftotext", "-f", str(n), "-l", str(n), pdf, "-"],
                         capture_output=True, text=True, encoding="utf-8",
                         errors="replace").stdout
    pages[n] = norm(txt)

hits = {n: 0 for n in pages}
missing = 0
for windows in prints:
    found = None
    for n, t in pages.items():
        if any(w and w in t for w in windows):
            found = n
            break
    if found:
        hits[found] += 1
    else:
        missing += 1

print(f"  {len(prints)} body paragraphs, {missing} not located")
bad = []
for n in sorted(hits):
    bar = "#" * hits[n]
    flag = "   <-- NO BODY PROSE" if hits[n] == 0 else ""
    print(f"  page {n:2d}: {hits[n]:2d} {bar}{flag}")
    if hits[n] == 0:
        bad.append(n)
print("  exhibit-only pages: " + (", ".join(map(str, bad)) if bad else "none"))
