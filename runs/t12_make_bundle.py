"""
t12_make_bundle.py — the Colab bundle and notebook for scoring tiers 1 and 2
(RUN_DECISIONS D19, "tiers 1 and 2 design").

texts.jsonl lists every unit the GPU scores, dev first, as the texts the
attacker sees in masked-alias order and nothing else (no id, label or truth):
    dev        the 46 dev pools tiers 0 and 3 were tuned on (runs/t3_dev.unit_view)
    headlineJ  the 46 headline Game J pools (runs/t3_units.j_prepare / j_texts)
    headlineO  the 100 headline Game O documents (runs/t3_units.o_texts)
Refuses to run with uncommitted changes to a bundled file.

    python runs/t12_make_bundle.py --out DIR
"""

import argparse
import hashlib
import json
import os
import subprocess
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
for d in ("adversaries", "harness", "analysis", "runs"):
    sys.path.insert(0, os.path.join(ROOT, d))

import t3_dev as D3                                            # noqa: E402
import t3_units as U                                           # noqa: E402

FILES = ["adversaries/crossenc_t3.py", "adversaries/lm_pmi_t12.py", "harness/masking.py", "runs/t12_score.py"]
NB = os.path.join("notebooks", "t12_colab.ipynb")

CELLS_NB = [
    ("markdown", "# Tiers 1 and 2: zero-shot language-model pair scores (GPU)\n\n"
     "RUN_DECISIONS D19, \"tiers 1 and 2 design\". Needs `t12_bundle.zip` in `My Drive/fragmentation_t12/`. "
     "Use an A100 runtime. Re-running resumes: scored units are skipped. When it prints "
     "`T12 SCORING COMPLETE`, zip `out/` is not needed: the laptop reads `My Drive/fragmentation_t12/out/`."),
    ("code", "from google.colab import drive\ndrive.mount('/content/drive')"),
    ("code", "import os, zipfile, subprocess, json\n"
     "BASE = '/content/drive/MyDrive/fragmentation_t12'\n"
     "OUT = BASE + '/out'\n"
     "assert os.path.exists(BASE + '/t12_bundle.zip'), 't12_bundle.zip is not in ' + BASE\n"
     "zipfile.ZipFile(BASE + '/t12_bundle.zip').extractall('/content/t12')\n"
     "print(json.load(open('/content/t12/BUNDLE.json')))\n"
     "print(subprocess.run(['nvidia-smi', '--query-gpu=name,memory.total', '--format=csv,noheader'], "
     "capture_output=True, text=True).stdout or 'NO GPU')"),
    ("code", "# smoke test: first 2 units, both tiers (timing only; full runs resume past them)\n"
     "!cd /content/t12 && python -u runs/t12_score.py --tier T1 --out \"$OUT\" --limit 2\n"
     "!cd /content/t12 && python -u runs/t12_score.py --tier T2 --out \"$OUT\" --limit 2"),
    ("code", "!cd /content/t12 && python -u runs/t12_score.py --tier T1 --out \"$OUT\""),
    ("code", "!cd /content/t12 && python -u runs/t12_score.py --tier T2 --out \"$OUT\""),
    ("code", "for t in ('T1', 'T2'):\n"
     "    r = json.load(open(f'{OUT}/{t}/SCORE_DONE.json'))\n"
     "    print(t, {k: v for k, v in r.items() if k != 'manifest'})\n"
     "print('T12 SCORING COMPLETE')"),
]


def notebook():
    cells = []
    for kind, src in CELLS_NB:
        c = {"cell_type": kind, "metadata": {}, "source": src.splitlines(keepends=True)}
        if kind == "code":
            c.update(execution_count=None, outputs=[])
        cells.append(c)
    return {"nbformat": 4, "nbformat_minor": 5, "cells": cells,
            "metadata": {"accelerator": "GPU", "colab": {"provenance": [], "gpuType": "A100"},
                         "kernelspec": {"name": "python3", "display_name": "Python 3"},
                         "language_info": {"name": "python"}}}


def unit_texts():
    rows = []
    for pid, frags, _truth in D3.dev_pools(None, False):
        rows.append({"kind": "J", "game": "dev", "unit": pid, "texts": D3.unit_view(frags)[3]})
    for game, cell, pid, members in U.j_units():
        if game == "headlineJ":
            _f, _k, _t, shown, _n, ms = U.j_prepare(cell, pid, members)
            rows.append({"kind": "J", "game": game, "unit": pid, "texts": U.j_texts(shown, ms)})
    for game, cell, rid, frags, _key in U.o_units():
        if game == "headlineO":
            rows.append({"kind": "O", "game": game, "unit": rid, "texts": U.o_texts(frags)})
    n = {g: sum(1 for r in rows if r["game"] == g) for g in ("dev", "headlineJ", "headlineO")}
    assert n == {"dev": 46, "headlineJ": 46, "headlineO": 100}, n
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    new = json.dumps(notebook(), indent=1) + "\n"
    if not os.path.exists(NB) or open(NB, encoding="utf-8").read() != new:
        open(NB, "w", encoding="utf-8", newline="\n").write(new)
        print(f"wrote {NB} (commit it, then run this again)")
    dirty = subprocess.run(["git", "status", "--porcelain", "--"] + FILES + [NB, "runs/t12_make_bundle.py"],
                           capture_output=True, text=True).stdout.strip()
    if dirty:
        raise SystemExit("STOP: commit these before bundling:\n" + dirty)
    commit = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    rows = unit_texts()
    body = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows).encode("utf-8")
    sha = hashlib.sha256(body).hexdigest()
    os.makedirs(a.out, exist_ok=True)
    manifest = {"units": [{k: r[k] for k in ("kind", "game", "unit")} | {"n": len(r["texts"])} for r in rows]}
    json.dump({"texts_sha256": sha, **manifest}, open(os.path.join(a.out, "t12_texts_manifest.json"), "w"), indent=1)
    zp = os.path.join(a.out, "t12_bundle.zip")
    with zipfile.ZipFile(zp, "w", zipfile.ZIP_DEFLATED) as z:
        for f in FILES:
            z.write(f, f)
        z.writestr("texts.jsonl", body)
        z.writestr("BUNDLE.json", json.dumps({"commit": commit, "texts_sha256": sha, "units": len(rows)}))
    print(f"{zp}: {len(rows)} units, texts sha {sha[:12]}, commit {commit[:12]}, {os.path.getsize(zp) / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
