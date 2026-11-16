"""
similar_make_bundle.py — the Colab bundle for scoring the similar pools with
tiers 1, 2 and 3 (RUN_DECISIONS D20, POST-HOC EXPLORATORY).

texts.jsonl holds each similar pool's texts in masked-alias order, with no id,
label or truth, exactly as every other attacker is shown them (runs/t3_units
j_prepare / j_texts: same cell, shown order and masking seeds as the Sonnet
spec runs/similar_J.json). The bundle carries only the scoring code. Refuses
if a bundled file is uncommitted.

    python runs/similar_make_bundle.py --out models/similar
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
for d in ("adversaries", "harness", "runs"):
    sys.path.insert(0, os.path.join(ROOT, d))

import t3_units as U                                           # noqa: E402

GAME = "similarJ"
FRAME = os.path.join("data", "pools", "similar_pools.json")
FILES = ["adversaries/crossenc_t3.py", "adversaries/lm_pmi_t12.py", "harness/masking.py",
         "runs/t12_score.py", "runs/similar_score_t3.py"]
NB = os.path.join("notebooks", "similar_colab.ipynb")

CELLS_NB = [
    ("markdown", "# Similar pools: pair scores for tiers 3, 1 and 2 (GPU)\n\n"
     "RUN_DECISIONS D20, post-hoc exploratory. Needs `similar_bundle.zip` in `My Drive/fragmentation_similar/` "
     "and the tier 3 model in `My Drive/fragmentation_t3/out/model/`. Re-running resumes: scored units are "
     "skipped. Each tier is its own cell; tier 2 is the slow one."),
    ("code", "from google.colab import drive\ndrive.mount('/content/drive')"),
    ("code", "import os, zipfile, subprocess, json\n"
     "BASE = '/content/drive/MyDrive/fragmentation_similar'\n"
     "OUT = BASE + '/out'\n"
     "T3MODEL = '/content/drive/MyDrive/fragmentation_t3/out/model'\n"
     "assert os.path.exists(BASE + '/similar_bundle.zip'), 'similar_bundle.zip is not in ' + BASE\n"
     "assert os.path.exists(T3MODEL + '/pair_model.safetensors'), 'tier 3 model is not in ' + T3MODEL\n"
     "zipfile.ZipFile(BASE + '/similar_bundle.zip').extractall('/content/sim')\n"
     "print(json.load(open('/content/sim/BUNDLE.json')))\n"
     "print(subprocess.run(['nvidia-smi', '--query-gpu=name,memory.total', '--format=csv,noheader'], "
     "capture_output=True, text=True).stdout or 'NO GPU')"),
    ("code", "# tier 3\n!cd /content/sim && python -u runs/similar_score_t3.py --model \"$T3MODEL\" --out \"$OUT\""),
    ("code", "# tier 1\n!cd /content/sim && python -u runs/t12_score.py --tier T1 --out \"$OUT\""),
    ("code", "# tier 2 (slow)\n!cd /content/sim && python -u runs/t12_score.py --tier T2 --out \"$OUT\""),
    ("code", "for t in ('T3', 'T1', 'T2'):\n"
     "    p = f'{OUT}/{t}/SCORE_DONE.json'\n"
     "    print(t, {k: v for k, v in json.load(open(p)).items() if k != 'manifest'} if os.path.exists(p) "
     "else 'NOT FINISHED')\n"
     "print('SIMILAR SCORING SUMMARY PRINTED')"),
]


def notebook():
    cells = []
    for kind, src in CELLS_NB:
        c = {"cell_type": kind, "metadata": {}, "source": src.splitlines(keepends=True)}
        if kind == "code":
            c.update(execution_count=None, outputs=[])
        cells.append(c)
    return {"nbformat": 4, "nbformat_minor": 5, "cells": cells,
            "metadata": {"accelerator": "GPU", "colab": {"provenance": [], "gpuType": "L4"},
                         "kernelspec": {"name": "python3", "display_name": "Python 3"},
                         "language_info": {"name": "python"}}}


def pools():
    frame = json.load(open(FRAME, encoding="utf-8"))
    return [(p["pool_id"], p["members"]) for p in frame["pools"]]


def cell_dir():
    (cell,) = json.load(open(os.path.join("runs", "final_headlineJ.json"), encoding="utf-8"))["build"]["cells"]
    return cell


def unit_texts():
    """One row per similar pool: its texts in masked-alias order."""
    rows = []
    cell = cell_dir()
    for pid, members in pools():
        _f, _k, _t, shown, _n, ms = U.j_prepare(cell, pid, members)
        rows.append({"kind": "eval", "game": GAME, "unit": pid, "texts": U.j_texts(shown, ms)})
    assert len(rows) == 46, len(rows)
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    new = json.dumps(notebook(), indent=1) + "\n"
    if not os.path.exists(NB) or open(NB, encoding="utf-8").read() != new:
        open(NB, "w", encoding="utf-8", newline="\n").write(new)
        print(f"wrote {NB} (commit it, then run this again)")
    dirty = subprocess.run(["git", "status", "--porcelain", "--"] + FILES + [NB, FRAME, "runs/similar_make_bundle.py"],
                           capture_output=True, text=True).stdout.strip()
    if dirty:
        raise SystemExit("STOP: commit these before bundling:\n" + dirty)
    commit = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    rows = unit_texts()
    body = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows).encode("utf-8")
    sha = hashlib.sha256(body).hexdigest()
    os.makedirs(a.out, exist_ok=True)
    zp = os.path.join(a.out, "similar_bundle.zip")
    with zipfile.ZipFile(zp, "w", zipfile.ZIP_DEFLATED) as z:
        for f in FILES:
            z.write(f, f)
        z.writestr("texts.jsonl", body)
        z.writestr("BUNDLE.json", json.dumps({"commit": commit, "texts_sha256": sha, "units": len(rows)}))
    n_pairs = sum(len(r["texts"]) * (len(r["texts"]) - 1) for r in rows)
    print(f"{zp}: {len(rows)} pools, {n_pairs:,} ordered pairs, texts sha {sha[:12]}, commit {commit[:12]}, "
          f"{os.path.getsize(zp) / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
