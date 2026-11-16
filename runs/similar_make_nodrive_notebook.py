"""
similar_make_nodrive_notebook.py — a Colab notebook for the similar-pools
scoring pass that needs no Google Drive mount (RUN_DECISIONS D20). Convenience
only: the same bundle (models/similar/similar_bundle.zip, built by
runs/similar_make_bundle.py) is embedded in the notebook as base64, and each
tier's scores are downloaded through the browser when it finishes. The scoring
code, texts and hashes are those of the bundle; nothing else changes.

Tier 3 needs its trained model folder (My Drive/fragmentation_t3/out/model/).
With --model-link, the notebook fetches it from a Drive share link with gdown;
without it, the notebook expects a zip of that folder dragged into /content.
runs/similar_score_t3.py checks the weights against the recorded hashes either
way. The link is passed on the command line so that it is never committed.

Writes models/similar/similar_colab_nodrive.ipynb (not committed: it carries
the bundle and, if given, the link).

    python runs/similar_make_nodrive_notebook.py [--model-link <drive folder link>]
"""

import argparse
import base64
import hashlib
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
ZIP = os.path.join("models", "similar", "similar_bundle.zip")
OUT = os.path.join("models", "similar", "similar_colab_nodrive.ipynb")

DL = ("shutil.make_archive('/content/similar_{t}', 'zip', OUT, '{t}')\n"
      "files.download('/content/similar_{t}.zip')")
FIND_MODEL = ("T3MODEL = os.path.dirname(glob.glob('/content/t3model/**/pair_model.safetensors', "
              "recursive=True)[0])\n")
SCORE_T3 = "!cd /content/sim && python -u runs/similar_score_t3.py --model \"$T3MODEL\" --out \"$OUT\"\n"


def t3_cells(link):
    if link:
        link = link.split("?")[0]
        return [("code", "# tier 3: fetch the trained model from the share link, score, download the scores\n"
                 f"!gdown --folder \"{link}\" -O /content/t3model\n" + FIND_MODEL + SCORE_T3 + DL.format(t="T3"))]
    return [("markdown", "**Tier 3 needs its model.** Download the `model` folder from "
             "`My Drive/fragmentation_t3/out/` in a browser tab (Drive gives a zip), drag that zip into the file "
             "sidebar here so it lands in `/content`, wait for the upload to finish, then run the next cell."),
            ("code", "# tier 3, then download its scores\n"
             "z = sorted(glob.glob('/content/model*.zip'))[-1]\n"
             "zipfile.ZipFile(z).extractall('/content/t3model')\n" + FIND_MODEL + SCORE_T3 + DL.format(t="T3"))]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model-link", default="", help="Drive share link of the tier 3 model folder")
    ap.add_argument("--tier2-only", action="store_true",
                    help="write similar_colab_nodrive_T2.ipynb: tier 2 alone, for a separate runtime")
    a = ap.parse_args()
    raw = open(ZIP, "rb").read()
    sha = hashlib.sha256(raw).hexdigest()
    b64 = base64.b64encode(raw).decode("ascii")
    cells = [
        ("markdown", "# Similar pools without a Drive mount: tiers 3, 1 and (optionally) 2 (GPU)\n\n"
         "RUN_DECISIONS D20, post-hoc exploratory. The bundle is inside this notebook. Each tier downloads a zip "
         "when it finishes: keep them. Nothing is saved if the runtime drops mid-tier. `Run all` does tier 3, "
         "tier 1, then ends the runtime; tier 2 (about 3 hours) runs only if `RUN_T2 = True` in the first cell."),
        ("code", "RUN_T2 = False   # True adds tier 2, about 3 hours on an L4\n"
         "import os, zipfile, json, glob, shutil, base64, hashlib, subprocess, time\n"
         "from google.colab import files\n"
         "OUT = '/content/out'\n"
         f"BUNDLE_SHA = '{sha}'\n"
         f"raw = base64.b64decode('{b64}')\n"
         "assert hashlib.sha256(raw).hexdigest() == BUNDLE_SHA, 'embedded bundle is damaged'\n"
         "open('/content/similar_bundle.zip', 'wb').write(raw)\n"
         "zipfile.ZipFile('/content/similar_bundle.zip').extractall('/content/sim')\n"
         "print(json.load(open('/content/sim/BUNDLE.json')))\n"
         "print(subprocess.run(['nvidia-smi', '--query-gpu=name,memory.total', '--format=csv,noheader'], "
         "capture_output=True, text=True).stdout or 'NO GPU')"),
        *t3_cells(a.model_link),
        ("code", "# tier 1 (about 30 min on an L4), then download its scores\n"
         "!cd /content/sim && python -u runs/t12_score.py --tier T1 --out \"$OUT\"\n" + DL.format(t="T1")),
        ("code", "# tier 2, only if RUN_T2 is True (lost if the runtime drops), then download its scores\n"
         "if RUN_T2:\n"
         "    !cd /content/sim && python -u runs/t12_score.py --tier T2 --out \"$OUT\"\n"
         "    shutil.make_archive('/content/similar_T2', 'zip', OUT, 'T2')\n"
         "    files.download('/content/similar_T2.zip')\n"
         "else:\n"
         "    print('tier 2 skipped (RUN_T2 is False)')"),
        ("code", "# end the runtime (stops GPU billing) after giving the browser 3 minutes to finish the downloads\n"
         "for t in ['T3', 'T1'] + (['T2'] if RUN_T2 else []):\n"
         "    assert os.path.exists(f'{OUT}/{t}/SCORE_DONE.json'), t + ' not finished: runtime left running'\n"
         "time.sleep(180)\n"
         "from google.colab import runtime\nruntime.unassign()"),
    ]
    out = OUT
    if a.tier2_only:                       # tier 2 alone, for a second runtime after tiers 3 and 1 are home
        out = OUT.replace(".ipynb", "_T2.ipynb")
        cells = [
            ("markdown", "# Similar pools without a Drive mount: tier 2 only (GPU)\n\n"
             "RUN_DECISIONS D20, post-hoc exploratory. The bundle is inside this notebook. `Run all` scores tier 2, "
             "downloads `similar_T2.zip`, then ends the runtime. Nothing is saved if the runtime drops first."),
            ("code", cells[1][1].replace("RUN_T2 = False", "RUN_T2 = True", 1)),
            cells[-2],
            ("code", "# end the runtime (stops GPU billing) after giving the browser 3 minutes to finish the download\n"
             "assert os.path.exists(OUT + '/T2/SCORE_DONE.json'), 'T2 not finished: runtime left running'\n"
             "time.sleep(180)\n"
             "from google.colab import runtime\nruntime.unassign()"),
        ]
    nb_cells = []
    for kind, src in cells:
        c = {"cell_type": kind, "metadata": {}, "source": src.splitlines(keepends=True)}
        if kind == "code":
            c.update(execution_count=None, outputs=[])
        nb_cells.append(c)
    nb = {"nbformat": 4, "nbformat_minor": 5, "cells": nb_cells,
          "metadata": {"accelerator": "GPU", "colab": {"provenance": [], "gpuType": "L4"},
                       "kernelspec": {"name": "python3", "display_name": "Python 3"},
                       "language_info": {"name": "python"}}}
    open(out, "w", encoding="utf-8", newline="\n").write(json.dumps(nb, indent=1) + "\n")
    what = "tier 2 only" if a.tier2_only else f"tier 3 model by {'share link' if a.model_link else 'uploaded zip'}"
    print(f"{out}: bundle sha {sha[:12]} embedded, {what}, {os.path.getsize(out) / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
