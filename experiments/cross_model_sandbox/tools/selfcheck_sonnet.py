"""Re-score Sonnet's raw headline Game J answers with the frozen pipeline and
require the paper's numbers back. NO API CALLS.

    python tools/selfcheck_sonnet.py       (from experiments/cross_model_sandbox/)

This is the regression test for the sandbox. It goes from raw provider rows
(frozen/results/batches/) through the frozen parser, repair-round rebuild,
finalise, integrity gate and scorer, exactly as runs/final_run_steps123.py did,
into a temporary directory. It passes only if

  1. every unit's final answer equals the committed scored row
     (frozen/results/final/headlineJ/prose/J.jsonl), and
  2. the mean F1_J, F1_L and q over the 46 pools equal KEY_NUMBERS.json
     ("One-shot Sonnet", headline) to 1e-9.

A new model's results only mean the same thing as Sonnet's if they go through
this same path. If you change how rows are produced, run this again first.
"""
import contextlib
import io
import json
import os
import shutil
import statistics as st
import sys
import tempfile

SB = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FROZEN = os.path.join(SB, "frozen")
for d in ("adversaries", "harness", "analysis"):
    sys.path.insert(0, os.path.join(FROZEN, d))

from batch_game import build_repair_spec, score        # noqa: E402
from joint_game import build_units, score_row          # noqa: E402

B = os.path.join(FROZEN, "results", "batches")


def main():
    spec = json.load(open(os.path.join(FROZEN, "runs", "final_headlineJ.json"), encoding="utf-8"))
    base_files = [os.path.join(B, "final-headlineJ.results.jsonl"),
                  os.path.join(B, "final-headlineJ-rs1.results.jsonl")]
    rp = build_repair_spec([(spec, base_files)], 1, 1, "final-headlineJ-r1")
    waves = [(spec, base_files), (rp, [os.path.join(B, "final-headlineJ-r1.results.jsonl")])]

    tmp = tempfile.mkdtemp(prefix="selfcheck_")
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            verdict = score(waves, tmp)
        assert not any(verdict.values()), f"gate refused: {verdict}"
        mine = {r["unit"]: r for r in map(json.loads, open(os.path.join(tmp, "prose", "J.jsonl"),
                                                           encoding="utf-8"))}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    ref = {r["unit"]: r for r in map(json.loads, open(
        os.path.join(FROZEN, "results", "final", "headlineJ", "prose", "J.jsonl"), encoding="utf-8"))}
    assert set(mine) == set(ref), "different units"
    diff = [u for u in ref if mine[u]["raw_response"] != ref[u]["raw_response"]]
    assert not diff, f"final answers differ for {diff[:5]}"
    print(f"1. re-scored {len(mine)} units from raw rows; every final answer equals the committed row "
          f"({len(rp['requests'])} repair requests rebuilt)")

    f1, fl, q = [], [], []
    for pid, members in spec["build"]["pools"]:
        _o, _u, key, truth = build_units(os.path.join(FROZEN, "data", "prose"), 0, len(members), 42,
                                         pools=[(pid, members)], o_docs=[])
        s = score_row(mine[pid], key, truth)
        f1.append(s["joint_f1"])
        fl.append(s["j_linkage_f1"])
        q.append(s["q"])
    kn = json.load(open(os.path.join(FROZEN, "results", "final_analysis", "KEY_NUMBERS.json"),
                        encoding="utf-8"))["headline"]["One-shot Sonnet"]
    got = {"F1_J_mean": st.fmean(f1), "F1_L_mean": st.fmean(fl), "q_mean": st.fmean(q)}
    for k, v in got.items():
        assert abs(v - kn[k]) < 1e-9, f"{k}: re-scored {v} vs paper {kn[k]}"
    print("2. headline means match KEY_NUMBERS.json: "
          + ", ".join(f"{k} {v:.4f}" for k, v in got.items()))
    print("SELF-CHECK PASSED")


if __name__ == "__main__":
    main()
