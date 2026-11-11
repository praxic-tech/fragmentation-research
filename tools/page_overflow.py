r"""Report, per page, how far below the text block any ink reaches (spill)."""
import os
import subprocess
import sys
import tempfile

pdf = sys.argv[1]
out = subprocess.run(["pdfinfo", pdf], capture_output=True, text=True).stdout
npages = int([l for l in out.splitlines() if l.startswith("Pages")][0].split()[-1])
tmp = tempfile.mkdtemp()

BOT = 992          # bottom of the text block at 100 dpi
FOOT = 1010        # the folio sits here; ignore it


def read_pbm(path):
    data = open(path, "rb").read()
    parts, i = [], 2
    while len(parts) < 2:
        while data[i:i + 1].isspace():
            i += 1
        j = i
        while not data[j:j + 1].isspace():
            j += 1
        parts.append(int(data[i:j]))
        i = j
    i += 1
    w, h = parts
    return w, h, (w + 7) // 8, data[i:]


for p in range(1, npages + 1):
    base = os.path.join(tmp, "p%d" % p)
    subprocess.run(["pdftoppm", "-mono", "-r", "100", "-f", str(p), "-l", str(p),
                    pdf, base], check=True)
    f = [x for x in os.listdir(tmp) if x.startswith("p%d-" % p)][0]
    w, h, stride, bits = read_pbm(os.path.join(tmp, f))
    low = 0
    for y in range(BOT, min(h, 1080)):
        if y in range(FOOT - 8, FOOT + 10):
            continue
        row = bits[y * stride:(y + 1) * stride]
        for x in range(72, min(778, w)):
            if row[x >> 3] & (0x80 >> (x & 7)):
                low = y
                break
    if low:
        print("  page %2d: ink %3dpx below the text block" % (p, low - BOT))
print("done")
