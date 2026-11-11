r"""
Measure real whitespace, not word counts: for each page, render to PBM and
report how far down each column the last ink sits, as a percentage of the text
block. Word counts mislead here because a table's notes are hundreds of words.

Usage: ink.py <pdf> [firstpage lastpage]
"""
import os
import subprocess
import sys
import tempfile

pdf = sys.argv[1]
first = int(sys.argv[2]) if len(sys.argv) > 2 else 1
last = int(sys.argv[3]) if len(sys.argv) > 3 else 99

out = subprocess.run(["pdfinfo", pdf], capture_output=True, text=True).stdout
npages = int([l for l in out.splitlines() if l.startswith("Pages")][0].split()[-1])
last = min(last, npages)

tmp = tempfile.mkdtemp()


def read_pbm(path):
    with open(path, "rb") as f:
        data = f.read()
    # P4 binary pbm
    parts = []
    i = 2
    while len(parts) < 2:
        while data[i:i + 1].isspace():
            i += 1
        if data[i:i + 1] == b"#":
            while data[i:i + 1] != b"\n":
                i += 1
            continue
        j = i
        while not data[j:j + 1].isspace():
            j += 1
        parts.append(int(data[i:j]))
        i = j
    i += 1
    w, h = parts
    stride = (w + 7) // 8
    return w, h, stride, data[i:]


print(f"{'page':>4}  {'left col':>9}  {'right col':>9}   (last ink, % of text block)")
for p in range(first, last + 1):
    base = os.path.join(tmp, f"p{p}")
    subprocess.run(["pdftoppm", "-mono", "-r", "100", "-f", str(p), "-l", str(p),
                    pdf, base], check=True)
    f = [x for x in os.listdir(tmp) if x.startswith(f"p{p}-")][0]
    w, h, stride, bits = read_pbm(os.path.join(tmp, f))

    # text block, measured from the rendered page at 100 dpi (letter, acmart)
    top, bot = 118, 990
    # skip the review line-number gutters: they have ink on every line
    cols = {"left": (72, 410), "right": (438, 776)}
    res = {}
    for name, (x0, x1) in cols.items():
        lastrow = top
        for y in range(top, min(bot, h)):
            row = bits[y * stride:(y + 1) * stride]
            ink = False
            for x in range(x0, min(x1, w)):
                if row[x >> 3] & (0x80 >> (x & 7)):
                    ink = True
                    break
            if ink:
                lastrow = y
        res[name] = 100.0 * (lastrow - top) / (bot - top)
    print(f"{p:>4}  {res['left']:8.0f}%  {res['right']:8.0f}%")
