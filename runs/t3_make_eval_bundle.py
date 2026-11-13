"""
t3_make_eval_bundle.py — the code + evaluation-unit bundle and notebook for
scoring tier 3's evaluation pairs on Colab (RUN_DECISIONS D19, "tier 3
tuning, fixed before the evaluation run").

Contains the repository's Python at the current commit, the build files that
define every evaluation unit, and each unit cell's fragment and answer-key
files (build_units reads both; the scorer only uses fragment texts).
Refuses to run with uncommitted changes to a bundled file.

    python runs/t3_make_eval_bundle.py --out DIR
"""

import argparse
import glob
import json
import os
import subprocess
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)

import sys                                                     # noqa: E402
sys.path.insert(0, os.path.join(ROOT, "runs"))
import t3_units as U                                           # noqa: E402

BUILDS = sorted({p for _g, ps in U.J_GAMES + U.O_GAMES for p in ps})
CELLS = sorted({c for b in BUILDS for c in json.load(open(b, encoding="utf-8"))["build"]["cells"]})
FILES = (sorted(glob.glob("adversaries/*.py"))
         + sorted(f for f in glob.glob("harness/*.py") if not os.path.basename(f).startswith("test_"))
         + ["runs/t3_units.py", "runs/t3_score_eval.py"] + BUILDS
         + [os.path.join(c, f).replace("\\", "/") for c in CELLS
            for f in ("prose_fragments.jsonl", "prose_answer_key.jsonl")])

CELLS_NB = [
    ("markdown", "# Tier 3: score every evaluation pair (GPU)\n\n"
     "RUN_DECISIONS D19, \"tier 3 tuning, fixed before the evaluation run\". Needs in `My Drive/fragmentation_t3/`: "
     "`t3_eval_bundle.zip` and the training run's `out/model/`. Re-running resumes: scored units are skipped."),
    ("code", "from google.colab import drive\ndrive.mount('/content/drive')"),
    ("code", "import os, zipfile, subprocess\n"
     "BASE = '/content/drive/MyDrive/fragmentation_t3'\n"
     "OUT = BASE + '/out'\n"
     "assert os.path.exists(BASE + '/t3_eval_bundle.zip'), 't3_eval_bundle.zip is not in ' + BASE\n"
     "zipfile.ZipFile(BASE + '/t3_eval_bundle.zip').extractall('/content/t3e')\n"
     "print('bundle commit:', open('/content/t3e/BUNDLE_COMMIT.txt').read().strip())\n"
     "print(subprocess.run(['nvidia-smi', '--query-gpu=name,memory.total', '--format=csv,noheader'], "
     "capture_output=True, text=True).stdout or 'NO GPU')"),
    ("code", "!pip -q install python-dotenv openai"),
    ("code", "!cd /content/t3e && python -u runs/t3_score_eval.py --model \"$OUT/model\" --out \"$OUT\" --limit 3"),
    ("code", "!cd /content/t3e && python -u runs/t3_score_eval.py --model \"$OUT/model\" --out \"$OUT\""),
    ("code", "import json\nr = json.load(open(OUT + '/SCORE_DONE.json'))\n"
     "print({k: v for k, v in r.items() if k != 'manifest'})\nprint('T3 EVAL SCORING COMPLETE')"),
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    nb_p = os.path.join("notebooks", "t3_eval_colab.ipynb")
    new = json.dumps(notebook(), indent=1) + "\n"
    if not os.path.exists(nb_p) or open(nb_p, encoding="utf-8").read() != new:
        open(nb_p, "w", encoding="utf-8", newline="\n").write(new)
        print(f"wrote {nb_p} (commit it, then run this again)")
    missing = [f for f in FILES if not os.path.exists(f)]
    if missing:
        raise SystemExit(f"STOP: missing {missing[:5]}")
    dirty = subprocess.run(["git", "status", "--porcelain", "--"] + FILES + [nb_p, "runs/t3_make_eval_bundle.py"],
                           capture_output=True, text=True).stdout.strip()
    if dirty:
        raise SystemExit("STOP: commit these before bundling:\n" + dirty)
    commit = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    os.makedirs(a.out, exist_ok=True)
    zp = os.path.join(a.out, "t3_eval_bundle.zip")
    with zipfile.ZipFile(zp, "w", zipfile.ZIP_DEFLATED) as z:
        for f in FILES:
            z.write(f, f.replace("\\", "/"))
        z.writestr("BUNDLE_COMMIT.txt", commit + "\n")
    print(f"{zp}: {len(FILES)} files at commit {commit[:12]}, {os.path.getsize(zp) / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
