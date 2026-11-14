"""
final_run_similar.py — POST-HOC EXPLORATORY — SIMILAR POOLS, one-shot Sonnet,
game J only (RUN_DECISIONS D20).

Submits exactly the frozen spec runs/similar_J.json, after verifying its
SHA-256 against its manifest and that no frozen artifact differs from the
freezing commit. Driver, ledger controls, one transport resend,
resends-before-repairs, the one structural repair round and the D6 RBNC rule
are the unchanged steps 1-5 path (runs/final_run_steps123.Run), as for every
other paid run. Scored with the ordinary J scorer and the corrected integrity
gate into results/final/similarJ/.

The real run needs --max-spend: the ledger reserves 2x the expected cost
($26.66), which is over the $182 tripwire set in D11. Raising it is the user's
decision; the $197.64 hard wall is unchanged and holds the worst case.

    python runs/final_run_similar.py --rehearse                 # fake provider, temp dirs, $0
    python runs/final_run_similar.py --max-spend 190            # the approved run
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

FREEZE = "1de447b327188c45d43a9e666756a9748419df0d"
SPEC = "runs/similar_J.json"
MANIFEST = "runs/similar_J_manifest.json"
FROZEN_PATHS = [SPEC, MANIFEST, "data/pools/similar_pools.json", "runs/similar_pools.py",
                "runs/build_similar_spec.py", "data/prose"]
GAMES = [("similarJ", [SPEC])]
LABEL = "similar pools game J (D20)"


def verify_frozen():
    man = json.load(open(MANIFEST, encoding="utf-8"))
    got = hashlib.sha256(open(SPEC, "rb").read()).hexdigest()
    if got != man["spec_sha256"]:
        raise SystemExit(f"STOP: {SPEC} does not match its frozen manifest hash. Nothing was sent.")
    if subprocess.run(["git", "diff", "--quiet", FREEZE, "--"] + FROZEN_PATHS).returncode != 0:
        raise SystemExit(f"STOP: a frozen artifact differs from the freezing commit {FREEZE[:7]}. Nothing was sent.")
    n = len(json.load(open(SPEC, encoding="utf-8"))["requests"])
    if n != 46:
        raise SystemExit(f"STOP: the frozen spec has {n} requests, not 46. Nothing was sent.")
    print(f"frozen spec verified: {SPEC} sha256 {got[:12]}, 46 requests, unchanged since {FREEZE[:7]}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rehearse", action="store_true")
    ap.add_argument("--max-spend", type=float, default=None)
    a = ap.parse_args()
    verify_frozen()
    if a.rehearse:
        tmp = tempfile.mkdtemp(prefix="similar_rehearse_")
        try:
            client = _O(messages=_O(batches=_FakeBatches(holes=(3, 30))))
            led = Ledger(os.path.join(tmp, "ledger.json"), max_spend=DEFAULT_MAX_SPEND)
            Run(client, os.path.join(tmp, "batches"), led, AnswerStore(os.path.join(tmp, "store.jsonl")),
                os.path.join(tmp, "final"), poll=0, spend_order=[SPEC], games=GAMES, label=LABEL).run()
            steps = led.data["steps"]
            rep = os.path.join(tmp, "final", "similarJ", "REPORT.txt")
            print(f"REHEARSAL: {len(steps)} batches {list(steps)}; every one settled: "
                  f"{all(s.get('settled') for s in steps.values())}; report written: {os.path.exists(rep)}")
            print(open(rep, encoding="utf-8").read()[:1500])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        return
    if a.max_spend is None:
        raise SystemExit("STOP: the real run needs --max-spend (the user's decision; see the docstring).")
    try:
        Run(make_client(), DEFAULT_STATE_DIR, Ledger(max_spend=a.max_spend), AnswerStore(),
            os.path.join("results", "final"), poll=60, spend_order=[SPEC], games=GAMES, label=LABEL).run()
    except CreditStop as stop:
        print(f"\nSTOPPED CLEANLY: {stop}")
        sys.exit(2)


if __name__ == "__main__":
    main()
