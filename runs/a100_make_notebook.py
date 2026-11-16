"""
a100_make_notebook.py — one Colab notebook (no Drive mount) for four A100
scoring jobs, POST-HOC EXPLORATORY (RUN_DECISIONS D20 addenda of 2026-11-16
and D22):

    1. tier 1 on headline Game J            (D20: matched-hardware rescore)
    2. tier 3 on the pool-size sweep pools  (D22)
    3. tier 2 on the similar pools          (D20, pending)
    4. tier 2 on headline Game J            (D20: matched-hardware rescore)

Three bundles are embedded in the notebook as base64, each with the same
scoring code as the similar-pools bundle and its own texts.jsonl:
    headline  46 headline Game J pools (texts as the L4 runs scored them)
    similar   models/similar/similar_bundle.zip, unchanged
    sweep     the D22 pools of data/pools/nsweep_pools.json, except N = 7
Texts are in masked-alias order with no id, label or truth
(runs/t3_units j_prepare / j_texts). Each job downloads a zip of its scores
when it finishes. The tier 3 model comes from a Drive share link passed with
--model-link (never committed) or, without it, from an uploaded zip.

Refuses if a bundled file is uncommitted. Writes models/a100/ (not committed).

    python runs/a100_make_notebook.py [--model-link <drive folder link>]
"""

import argparse
import base64
import hashlib
import io
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

FILES = ["adversaries/crossenc_t3.py", "adversaries/lm_pmi_t12.py", "harness/masking.py",
         "runs/t12_score.py", "runs/similar_score_t3.py"]
SPEC = os.path.join("runs", "final_headlineJ.json")
FRAME = os.path.join("data", "pools", "nsweep_pools.json")
SIM_ZIP = os.path.join("models", "similar", "similar_bundle.zip")
OUTDIR = os.path.join("models", "a100")


def cell_dir():
    (cell,) = json.load(open(SPEC, encoding="utf-8"))["build"]["cells"]
    return cell


def _row(game, cell, pid, members):
    _f, _k, _t, shown, _n, ms = U.j_prepare(cell, pid, members)
    return {"kind": "J", "game": game, "unit": pid, "texts": U.j_texts(shown, ms)}


def headline_pools():
    return [(p, m) for p, m in json.load(open(SPEC, encoding="utf-8"))["build"]["pools"]]


def sweep_pools():
    """(size, pool id, members) for every D22 pool that is scored (N = 7 is the headline result)."""
    frame = json.load(open(FRAME, encoding="utf-8"))
    return [(int(n), r["pool_id"], r["members"]) for n, rows in frame["sizes"].items() if n != "7" for r in rows]


def headline_rows():
    cell = cell_dir()
    return [_row("headlineJ", cell, pid, members) for pid, members in headline_pools()]


def sweep_rows():
    cell = cell_dir()
    return [_row(f"nsweepJ_n{n:02d}", cell, pid, members) for n, pid, members in sweep_pools()]


def bundle(rows, commit):
    body = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows).encode("utf-8")
    sha = hashlib.sha256(body).hexdigest()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for f in FILES:
            z.write(f, f)
        z.writestr("texts.jsonl", body)
        z.writestr("BUNDLE.json", json.dumps({"commit": commit, "texts_sha256": sha, "units": len(rows)}))
    pairs = sum(len(r["texts"]) * (len(r["texts"]) - 1) for r in rows)
    return buf.getvalue(), {"units": len(rows), "pairs": pairs, "texts_sha256": sha}


DL = ("shutil.make_archive('/content/{name}', 'zip', {out}, '{t}')\n"
      "files.download('/content/{name}.zip')")
FIND_MODEL = ("T3MODEL = os.path.dirname(glob.glob('/content/t3model/**/pair_model.safetensors', "
              "recursive=True)[0])\n")


def cells(b64, shas, link):
    unpack = "".join(
        f"raw = base64.b64decode('{b64[k]}')\n"
        f"assert hashlib.sha256(raw).hexdigest() == '{shas[k]}', '{k} bundle is damaged'\n"
        f"zipfile.ZipFile(io.BytesIO(raw)).extractall('/content/{k}')\n"
        f"print('{k}', json.load(open('/content/{k}/BUNDLE.json')))\n" for k in ("headline", "similar", "sweep"))
    if link:
        fetch = f"!gdown --folder \"{link.split('?')[0]}\" -O /content/t3model\n"
    else:
        fetch = ("# upload a zip of My Drive/fragmentation_t3/out/model/ into /content first\n"
                 "zipfile.ZipFile(sorted(glob.glob('/content/model*.zip'))[-1]).extractall('/content/t3model')\n")
    return [
        ("markdown", "# A100 jobs without a Drive mount (post-hoc exploratory)\n\n"
         "RUN_DECISIONS D20 addenda of 2026-11-16 and D22. `Run all` does, in order: tier 1 on the headline pools "
         "(about 10 min), tier 3 on the pool-size sweep (about 45 min), tier 2 on the similar pools (about 1 h), "
         "tier 2 on the headline pools (about 1 h), then ends the runtime. Each job downloads a zip when it "
         "finishes: allow multiple downloads and keep all four. A job in progress is lost if the runtime is "
         "deleted; finished jobs are already downloaded."),
        ("code", "REQUIRE_A100 = True   # the headline rescore is a matched-hardware check: it needs an A100\n"
         "import os, io, zipfile, json, glob, shutil, base64, hashlib, subprocess, time\n"
         "from google.colab import files\n"
         "OUT_HL, OUT_SIM, OUT_SW = '/content/out_headline', '/content/out_similar', '/content/out_sweep'\n"
         "gpu = subprocess.run(['nvidia-smi', '--query-gpu=name,memory.total', '--format=csv,noheader'], "
         "capture_output=True, text=True).stdout.strip() or 'NO GPU'\n"
         "print(gpu)\n"
         "assert 'A100' in gpu or not REQUIRE_A100, 'not an A100: Runtime > Change runtime type > A100 GPU'\n"
         + unpack),
        ("code", "# 1/4 tier 1 on the headline pools, then download its scores\n"
         "!cd /content/headline && python -u runs/t12_score.py --tier T1 --out \"$OUT_HL\"\n"
         + DL.format(name="headline_a100_T1", out="OUT_HL", t="T1")),
        ("code", "# 2/4 tier 3 on the pool-size sweep: fetch the trained model, score, download the scores\n"
         + fetch + FIND_MODEL
         + "!cd /content/sweep && python -u runs/similar_score_t3.py --model \"$T3MODEL\" --out \"$OUT_SW\"\n"
         + DL.format(name="nsweep_T3", out="OUT_SW", t="T3")),
        ("code", "# 3/4 tier 2 on the similar pools, then download its scores\n"
         "!cd /content/similar && python -u runs/t12_score.py --tier T2 --out \"$OUT_SIM\"\n"
         + DL.format(name="similar_T2", out="OUT_SIM", t="T2")),
        ("code", "# 4/4 tier 2 on the headline pools, then download its scores\n"
         "!cd /content/headline && python -u runs/t12_score.py --tier T2 --out \"$OUT_HL\"\n"
         + DL.format(name="headline_a100_T2", out="OUT_HL", t="T2")),
        ("code", "# end the runtime (stops GPU billing) after giving the browser 5 minutes to finish the downloads\n"
         "for p in (OUT_HL + '/T1', OUT_SW + '/T3', OUT_SIM + '/T2', OUT_HL + '/T2'):\n"
         "    assert os.path.exists(p + '/SCORE_DONE.json'), p + ' not finished: runtime left running'\n"
         "time.sleep(300)\n"
         "from google.colab import runtime\nruntime.unassign()"),
    ]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model-link", default="", help="Drive share link of the tier 3 model folder")
    a = ap.parse_args()
    dirty = subprocess.run(["git", "status", "--porcelain", "--"] + FILES + [SPEC, FRAME, "runs/a100_make_notebook.py",
                           "runs/nsweep_frame.py", "runs/t3_units.py"], capture_output=True, text=True).stdout.strip()
    if dirty:
        raise SystemExit("STOP: commit these before bundling:\n" + dirty)
    commit = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    os.makedirs(OUTDIR, exist_ok=True)
    raw, info = {}, {}
    raw["headline"], info["headline"] = bundle(headline_rows(), commit)
    raw["sweep"], info["sweep"] = bundle(sweep_rows(), commit)
    raw["similar"] = open(SIM_ZIP, "rb").read()
    info["similar"] = json.loads(zipfile.ZipFile(SIM_ZIP).read("BUNDLE.json"))
    shas = {k: hashlib.sha256(v).hexdigest() for k, v in raw.items()}
    for k in ("headline", "sweep"):
        open(os.path.join(OUTDIR, f"{k}_bundle.zip"), "wb").write(raw[k])
    b64 = {k: base64.b64encode(v).decode("ascii") for k, v in raw.items()}
    nb_cells = []
    for kind, src in cells(b64, shas, a.model_link):
        c = {"cell_type": kind, "metadata": {}, "source": src.splitlines(keepends=True)}
        if kind == "code":
            c.update(execution_count=None, outputs=[])
        nb_cells.append(c)
    nb = {"nbformat": 4, "nbformat_minor": 5, "cells": nb_cells,
          "metadata": {"accelerator": "GPU", "colab": {"provenance": [], "gpuType": "A100", "machine_shape": "hm"},
                       "kernelspec": {"name": "python3", "display_name": "Python 3"},
                       "language_info": {"name": "python"}}}
    out = os.path.join(OUTDIR, "a100_colab.ipynb")
    open(out, "w", encoding="utf-8", newline="\n").write(json.dumps(nb, indent=1) + "\n")
    json.dump({"commit": commit, "bundles": {k: {"zip_sha256": shas[k], **info[k]} for k in raw}},
              open(os.path.join(OUTDIR, "BUNDLES.json"), "w", encoding="utf-8"), indent=1)
    for k in raw:
        print(f"{k:9s} zip sha {shas[k][:12]}  {info[k]}")
    print(f"{out}: commit {commit[:12]}, tier 3 model by {'share link' if a.model_link else 'uploaded zip'}, "
          f"{os.path.getsize(out) / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
