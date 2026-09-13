"""
final_run_steps45.py — steps 4-5 of the approved final run: headline O and grid
O (3 waves), released by the user 2026-09-13 (RUN_DECISIONS D12).

The same driver, protocol and order as steps 1-3 (runs/final_run_steps123.py):
every base batch fetched, then every resend of a transport hole, then the one
repair round (malformed / incomplete output only), then scoring into
results/final/<game>/REPORT.txt. A call that exhausts 128k is a non-completion
(D6): never resubmitted, never repaired. Resumable: a batch already submitted is
fetched, never paid for twice.

It STOPS after step 5. Whether the hierarchical attacker runs is decided after
these are scored.

    python runs/final_run_steps45.py --rehearse     # fake provider, temp dirs, $0
    python runs/final_run_steps45.py                # the real run
"""

import argparse
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "runs"))

from final_run_steps123 import CreditStop, Run, _FakeBatches, _O   # noqa: E402  (sets up paths)
from answer_store import AnswerStore                                 # noqa: E402
from batch_submit import DEFAULT_STATE_DIR, make_client              # noqa: E402
from run_ledger import DEFAULT_MAX_SPEND, Ledger                     # noqa: E402

GRID = [f"runs/final_gridO_w{k}.json" for k in (1, 2, 3)]
GAMES = [("headlineO", ["runs/final_headlineO.json"]), ("gridO", GRID)]
SPEND_ORDER = ["runs/final_headlineO.json"] + GRID
LABEL = "steps 4-5"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rehearse", action="store_true")
    a = ap.parse_args()
    if a.rehearse:
        tmp = tempfile.mkdtemp(prefix="final45_rehearse_")
        try:
            # headline O is requests 1-100, grid O wave 1 is 101-190: a hole in each
            client = _O(messages=_O(batches=_FakeBatches(holes=(3, 150))))
            led = Ledger(os.path.join(tmp, "ledger.json"), max_spend=DEFAULT_MAX_SPEND)
            Run(client, os.path.join(tmp, "batches"), led, AnswerStore(os.path.join(tmp, "store.jsonl")),
                os.path.join(tmp, "final"), poll=0, spend_order=SPEND_ORDER, games=GAMES,
                label=LABEL).run()
            reports = [os.path.exists(os.path.join(tmp, "final", g, "REPORT.txt")) for g, _ in GAMES]
            steps = led.data["steps"]
            order = list(steps)
            resends = [i for i, t in enumerate(order) if t.endswith("-rs1") and "-r1" not in t]
            repairs = [i for i, t in enumerate(order) if "-r1" in t]
            first = len(resends) >= 2 and bool(repairs) and max(resends) < min(repairs)
            print(f"REHEARSAL: {len(steps)} batches, every one settled: "
                  f"{all(s.get('settled') for s in steps.values())}; reports written: {all(reports)}")
            print(f"  submission order: {order}")
            print(f"  all {len(resends)} resend batches before all {len(repairs)} repair batches: {first}")
            for g, _ in GAMES:
                print(f"\n--- rehearsal {g}/REPORT.txt (fake answers) ---")
                print(open(os.path.join(tmp, "final", g, "REPORT.txt"), encoding="utf-8").read()[:1500])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        return
    try:
        Run(make_client(), DEFAULT_STATE_DIR, Ledger(max_spend=DEFAULT_MAX_SPEND), AnswerStore(),
            os.path.join("results", "final"), poll=60, spend_order=SPEND_ORDER, games=GAMES,
            label=LABEL).run()
    except CreditStop as stop:
        print(f"\nSTOPPED CLEANLY: {stop}")
        sys.exit(2)


if __name__ == "__main__":
    main()
