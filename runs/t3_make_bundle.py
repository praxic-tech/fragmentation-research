"""
t3_make_bundle.py — the code bundle and notebook that go to Colab for tier 3
(RUN_DECISIONS D19, "tier 3 design").

The bundle is this repository's Python at the current commit, cut down to what
training and dev tuning import. It contains NO evaluation pool: only .py files
and tier 0's dev_tuning.json (dev pool membership, disjoint-corpus PMCIDs),
which t3_dev.py uses to check it rebuilt the same dev pools.

Refuses to run with uncommitted changes to a bundled file, so the recorded
commit really is the code that trains.

    python runs/t3_make_bundle.py --out DIR
"""

import argparse
import glob
import json
import os
import subprocess
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)

FILES = (sorted(glob.glob("adversaries/*.py"))
         + sorted(f for f in glob.glob("harness/*.py") if not os.path.basename(f).startswith("test_"))
         + ["runs/t0_dev.py", "runs/t3_train.py", "runs/t3_dev.py", "results/final_t0/dev_tuning.json"])

CELLS = [
    ("markdown", "# Tier 3 cross-encoder: train, tune the decoder on dev, export\n\n"
     "RUN_DECISIONS D19, \"tier 3 design\". Disjoint corpus only; this notebook and its bundle contain no evaluation pool.\n\n"
     "Needs in `My Drive/fragmentation_t3/`: `t3_code_bundle.zip`, `t3_training_data.zip`. "
     "Runtime: GPU (A100 preferred). Re-running after a disconnect resumes from the last checkpoint."),
    ("code", "from google.colab import drive\ndrive.mount('/content/drive')"),
    ("code", "import os, zipfile, subprocess, json\n"
     "BASE = '/content/drive/MyDrive/fragmentation_t3'\n"
     "OUT = BASE + '/out'\n"
     "os.makedirs(OUT, exist_ok=True)\n"
     "for z, dst in (('t3_code_bundle.zip', '/content/t3'), ('t3_training_data.zip', '/content/t3data')):\n"
     "    assert os.path.exists(f'{BASE}/{z}'), f'{z} is not in {BASE}'\n"
     "    zipfile.ZipFile(f'{BASE}/{z}').extractall(dst)\n"
     "print('bundle commit:', open('/content/t3/BUNDLE_COMMIT.txt').read().strip())\n"
     "print(subprocess.run(['nvidia-smi', '--query-gpu=name,memory.total', '--format=csv,noheader'], "
     "capture_output=True, text=True).stdout or 'NO GPU: set Runtime > Change runtime type > GPU')"),
    ("code", "!pip -q install python-dotenv openai onnx onnxruntime\n"
     "!pip list 2>/dev/null | grep -i -E '^(torch|transformers|tokenizers|onnx|onnxruntime|safetensors|scikit-learn|scipy|numpy) '"),
    ("code", "!cd /content/t3 && python -u runs/t3_train.py --data /content/t3data/documents.jsonl --out \"$OUT\""),
    ("code", "!cd /content/t3 && python -u runs/t3_dev.py --data /content/t3data/documents.jsonl --out \"$OUT\""),
    ("code", "rec = json.load(open(OUT + '/RECORD.json'))\n"
     "print(json.dumps({k: rec[k] for k in ('model_sha256', 'onnx_sha256', 'tokenizer_sha256', 'chosen', 'dev_T3', "
     "'bundle_commit')}, indent=1))\n"
     "print('T3 COLAB RUN COMPLETE')\n"
     "!ls -la \"$OUT\" \"$OUT/model\""),
]


def notebook():
    cells = []
    for kind, src in CELLS:
        c = {"cell_type": kind, "metadata": {}, "source": src.splitlines(keepends=True)}
        if kind == "code":
            c.update(execution_count=None, outputs=[])
        cells.append(c)
    return {"nbformat": 4, "nbformat_minor": 5, "cells": cells,
            "metadata": {"accelerator": "GPU", "colab": {"provenance": [], "machine_shape": "hm", "gpuType": "A100"},
                         "kernelspec": {"name": "python3", "display_name": "Python 3"},
                         "language_info": {"name": "python"}}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    os.makedirs("notebooks", exist_ok=True)
    nb_p = os.path.join("notebooks", "t3_colab.ipynb")
    new = json.dumps(notebook(), indent=1) + "\n"
    if not os.path.exists(nb_p) or open(nb_p, encoding="utf-8").read() != new:
        open(nb_p, "w", encoding="utf-8", newline="\n").write(new)
        print(f"wrote {nb_p} (commit it, then run this again)")
    dirty = subprocess.run(["git", "status", "--porcelain", "--"] + FILES + [nb_p, "runs/t3_make_bundle.py"],
                           capture_output=True, text=True).stdout.strip()
    if dirty:
        raise SystemExit("STOP: commit these before bundling, so the recorded commit is the code that runs:\n" + dirty)
    commit = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    os.makedirs(a.out, exist_ok=True)
    zp = os.path.join(a.out, "t3_code_bundle.zip")
    with zipfile.ZipFile(zp, "w", zipfile.ZIP_DEFLATED) as z:
        for f in FILES:
            z.write(f, f.replace("\\", "/"))
        z.writestr("BUNDLE_COMMIT.txt", commit + "\n")
    print(f"{zp}: {len(FILES)} files at commit {commit[:12]}, {os.path.getsize(zp) / 1e3:.0f} kB")


if __name__ == "__main__":
    main()
