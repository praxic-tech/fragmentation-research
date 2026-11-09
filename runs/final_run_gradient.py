"""
final_run_gradient.py — the POST-HOC EXPLORATORY — INTERMEDIATE GRANULARITY
GRADIENT (RUN_DECISIONS D18), game J only, on the frozen 20 pools / 140
documents / 60 requests across the three new arms (4, 3 and 2 words).

Submits exactly the frozen spec runs/gradient_J.json, after verifying its
SHA-256 against the frozen manifest and that no frozen artifact differs from
the freezing commit 97e7f66. The driver, ledger controls, one transport
resend, resends-before-repairs, the one structural repair round and the D6 RBNC
rule are the unchanged steps 1-5 path (runs/final_run_steps123.Run). An RBNC is
never re-asked, never resized, never replaced, never scored as zero.
Scored with the ordinary J scorer into results/final/gradientJ/.
NO GAME O, whatever the completion. It stops after game J.

Requires the user's explicit launch approval (D18). The freeze commit must
already be in history, which verify_frozen() enforces.

    python runs/final_run_gradient.py --rehearse    # fake provider, temp dirs, $0
    python runs/final_run_gradient.py               # the approved run
"""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "runs"))

from final_run_steps123 import CreditStop, Run, _FakeBatches, _O   # noqa: E402  (sets up paths, chdir)
from answer_store import AnswerStore                                 # noqa: E402
from batch_submit import DEFAULT_STATE_DIR, make_client              # noqa: E402
from run_ledger import DEFAULT_MAX_SPEND, Ledger                     # noqa: E402

FREEZE = "97e7f669418f73c73f05ffcd248e99a7bbb081ba"
SPEC = "runs/gradient_J.json"
MANIFEST = "runs/gradient_J_manifest.json"
FROZEN_PATHS = [SPEC, MANIFEST, "results/gradient",
                "data/pools/single_token_edge_pools.json",
                "results/single_token_edge/edge__token",
                "results/single_token_edge/edge__sentence",
                "harness/visible_metrics.py", "datagen/build_gradient_arms.py"]
GAMES = [("gradientJ", [SPEC])]
LABEL = "intermediate granularity gradient game J (D18)"
N_REQUESTS = 60


def verify_frozen():
    man = json.load(open(MANIFEST, encoding="utf-8"))
    got = hashlib.sha256(open(SPEC, "rb").read()).hexdigest()
    if got != man["spec_sha256"]:
        raise SystemExit(f"STOP: {SPEC} does not match its frozen manifest hash. Nothing was sent.")
    if subprocess.run(["git", "diff", "--quiet", FREEZE, "--"] + FROZEN_PATHS).returncode != 0:
        raise SystemExit(f"STOP: a frozen artifact differs from the freezing commit {FREEZE[:7]}. Nothing was sent.")
    spec = json.load(open(SPEC, encoding="utf-8"))
    n = len(spec["requests"])
    if n != N_REQUESTS:
        raise SystemExit(f"STOP: the frozen spec has {n} requests, not the approved {N_REQUESTS}. Nothing was sent.")
    cells = sorted({r["cell"] for r in spec["requests"]}) if "cell" in spec["requests"][0] else None
    print(f"frozen spec verified: {SPEC} sha256 {got[:12]}, {n} requests, "
          f"unchanged since {FREEZE[:7]}" + (f", cells {cells}" if cells else ""))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rehearse", action="store_true")
    a = ap.parse_args()
    verify_frozen()
    if a.rehearse:
        tmp = tempfile.mkdtemp(prefix="gradient_rehearse_")
        try:
            client = _O(messages=_O(batches=_FakeBatches(holes=(3, 30))))
            led = Ledger(os.path.join(tmp, "ledger.json"), max_spend=DEFAULT_MAX_SPEND)
            Run(client, os.path.join(tmp, "batches"), led, AnswerStore(os.path.join(tmp, "store.jsonl")),
                os.path.join(tmp, "final"), poll=0, spend_order=[SPEC], games=GAMES, label=LABEL).run()
            steps = led.data["steps"]
            rep = os.path.join(tmp, "final", "gradientJ", "REPORT.txt")
            print(f"REHEARSAL: {len(steps)} batches {list(steps)}; every one settled: "
                  f"{all(s.get('settled') for s in steps.values())}; report written: {os.path.exists(rep)}")
            if os.path.exists(rep):
                print(open(rep, encoding="utf-8").read()[:1200])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        return
    try:
        Run(make_client(), DEFAULT_STATE_DIR, Ledger(max_spend=DEFAULT_MAX_SPEND), AnswerStore(),
            os.path.join("results", "final"), poll=60, spend_order=[SPEC], games=GAMES, label=LABEL).run()
    except CreditStop as stop:
        print(f"\nSTOPPED CLEANLY: {stop}")
        sys.exit(2)


if __name__ == "__main__":
    main()
