r"""
One command for the four layout checks. Run it after any edit to Sections 4-5.

    python tools/check_layout.py            (from the repository root)

  page_map       every exhibit within one page of the section that discusses it
  page_prose     every body page carries running prose (no exhibit-only pages)
  page_overflow  nothing printed past the bottom margin
  page_attached  every table on the same page as its own notes

Exit status is non-zero if any of them fails.
"""
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(ROOT, "tools")
TEX = os.path.join(ROOT, "paper", "main.tex")
PDF = os.path.join(ROOT, "paper", "main.pdf")
TABLES = os.path.join(ROOT, "results", "paper_package", "tables")


def run(script, *args):
    return subprocess.run([sys.executable, "-I", os.path.join(TOOLS, script)] + list(args),
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace").stdout


npages = int(re.search(r"Pages:\s+(\d+)", subprocess.run(
    ["pdfinfo", PDF], capture_output=True, text=True).stdout).group(1))
failed = []

out = run("page_map.py", TEX, PDF)
far = int(re.search(r"from their section: (\d+)", out).group(1))
print("page_map       %s" % ("ok   every exhibit within one page of its section" if not far
                             else "FAIL %d exhibit(s) too far from their section" % far))
if far:
    print(out)
    failed.append("page_map")

out = run("page_prose.py", TEX, PDF)
bare = re.search(r"exhibit-only pages: (.*)", out).group(1)
# the last pages are the appendix; a page of appendix tables is expected there
appendix_from = None
for n in range(1, npages + 1):
    txt = subprocess.run(["pdftotext", "-f", str(n), "-l", str(n), PDF, "-"],
                         capture_output=True, text=True, encoding="utf-8",
                         errors="replace").stdout
    if re.search(r"(?m)^A\s+Design Summary", txt):
        appendix_from = n
        break
body_bare = [p for p in re.findall(r"\d+", bare)
             if appendix_from is None or int(p) <= appendix_from - 1]
print("page_prose     %s" % ("ok   every body page carries prose" if not body_bare
                             else "FAIL exhibit-only body page(s): " + ", ".join(body_bare)))
if body_bare:
    failed.append("page_prose")

out = run("page_overflow.py", PDF)
spill = [l.strip() for l in out.splitlines()
         if "px below" in l and int(re.search(r"(\d+)px", l).group(1)) > 8]
print("page_overflow  %s" % ("ok   nothing past the bottom margin" if not spill
                             else "FAIL " + "; ".join(spill)))
if spill:
    failed.append("page_overflow")

out = run("page_attached.py", TABLES, PDF)
det = int(re.search(r"detached: (\d+)", out).group(1))
print("page_attached  %s" % ("ok   every table with its notes" if not det
                             else "FAIL %d table(s) separated from their notes" % det))
if det:
    print(out)
    failed.append("page_attached")

print("%d pages; %s" % (npages, "all four checks pass" if not failed
                        else "FAILED: " + ", ".join(failed)))
sys.exit(1 if failed else 0)
