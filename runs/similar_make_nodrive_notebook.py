"""
similar_make_nodrive_notebook.py — a Colab notebook for the similar-pools
scoring pass that needs no Google Drive (RUN_DECISIONS D20). Convenience only:
the same bundle (models/similar/similar_bundle.zip, built by
runs/similar_make_bundle.py) is embedded in the notebook as base64, and each
tier's scores are downloaded through the browser when it finishes. The scoring
code, texts and hashes are those of the bundle; nothing else changes.

Tier 3 still needs its model folder: upload the zip of
My Drive/fragmentation_t3/out/model/ into /content with the file sidebar.

Writes models/similar/similar_colab_nodrive.ipynb (not committed: it carries
the bundle).

    python runs/similar_make_nodrive_notebook.py
"""

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


def main():
    raw = open(ZIP, "rb").read()
    sha = hashlib.sha256(raw).hexdigest()
    b64 = base64.b64encode(raw).decode("ascii")
    cells = [
        ("markdown", "# Similar pools without Google Drive: tiers 1, 3 and 2 (GPU)\n\n"
         "RUN_DECISIONS D20, post-hoc exploratory. The bundle is inside this notebook. Each tier downloads a zip "
         "when it finishes: keep them. Nothing is saved if the runtime drops mid-tier, so run one tier at a time."),
        ("code", "import os, zipfile, json, glob, shutil, base64, hashlib, subprocess\n"
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
        ("code", "# tier 1 (about 30 min on an L4), then download its scores\n"
         "!cd /content/sim && python -u runs/t12_score.py --tier T1 --out \"$OUT\"\n" + DL.format(t="T1")),
        ("markdown", "**Tier 3 needs its model.** Download the `model` folder from "
         "`My Drive/fragmentation_t3/out/` in a browser tab (Drive gives a zip), drag that zip into the file "
         "sidebar here so it lands in `/content`, wait for the upload to finish, then run the next cell."),
        ("code", "# tier 3, then download its scores\n"
         "z = sorted(glob.glob('/content/model*.zip'))[-1]\n"
         "zipfile.ZipFile(z).extractall('/content/t3model')\n"
         "T3MODEL = os.path.dirname(glob.glob('/content/t3model/**/pair_model.safetensors', recursive=True)[0])\n"
         "!cd /content/sim && python -u runs/similar_score_t3.py --model \"$T3MODEL\" --out \"$OUT\"\n"
         + DL.format(t="T3")),
        ("code", "# tier 2 (optional, about 3 hours on an L4; lost if the runtime drops), then download its scores\n"
         "!cd /content/sim && python -u runs/t12_score.py --tier T2 --out \"$OUT\"\n" + DL.format(t="T2")),
        ("code", "# end the runtime once the downloads have finished\n"
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
    open(OUT, "w", encoding="utf-8", newline="\n").write(json.dumps(nb, indent=1) + "\n")
    print(f"{OUT}: bundle sha {sha[:12]} embedded, {os.path.getsize(OUT) / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
