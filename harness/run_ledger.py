"""
run_ledger.py — durable run state and the spend cap.

Two problems this solves.

RESUME IS PER-TOOL, AND NOTHING KNOWS THE RUN
---------------------------------------------
run_grid resumes cells, batch_submit resumes a fetch, the adversary resumes
records. None of them knows what step the *run* is on, so a crash between tools
is recovered by a human remembering what had happened. One ledger records every
step's state and makes re-running always safe:

    pending -> submitted(batch_id) -> fetched -> scored
                                   \\-> failed

A batch id is written the moment it exists, before anything is billed, so a
process that dies after create() never loses a paid batch.

THE BALANCE IS NO LONGER A BACKSTOP
-----------------------------------
With a fixed prepayment, running out of credit is a hard physical limit on how
wrong things can go. With auto-reload it is not: a bug that resubmits in a loop
just keeps buying credit. So the cap moves into code, and it is consulted BEFORE
each submission using the projection rather than after the fact.

When the cap would be crossed, the run refuses and prints RUN_PLAN's documented
cut order rather than inventing one under pressure:

    repeats ($7.60) -> the clause row ($31) -> two granularity linkage cells

    python harness/run_ledger.py --status
    python harness/run_ledger.py --check-spend 60.61
"""

import argparse
import json
import os
from datetime import datetime, timezone

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(BASE_DIR)
DEFAULT_PATH = os.path.join(ROOT, "results", "run_ledger.json")

# RUN_PLAN's tripwire. Above the $149.82 modelled ceiling, below runaway.
DEFAULT_MAX_SPEND = 170.00

# Documented, in the order it should be applied. Not invented at the moment of
# refusal, when the temptation is to cut whatever is nearest.
CUT_ORDER = [
    ("repeats", 7.60, "reference cell x2, the variance bound"),
    ("clause row", 31.00, "4 clause cells; clause is also mispriced at 1.81x "
                          "when measured is ~1.31x"),
    ("granularity linkage cells", 5.62, "the two non-sentence linkage cells"),
]

STATES = ("pending", "submitted", "fetched", "scored", "failed")


def _now():
    return datetime.now(timezone.utc).isoformat()


class Ledger:
    """One JSON file, written atomically, describing the whole run."""

    def __init__(self, path=DEFAULT_PATH, max_spend=DEFAULT_MAX_SPEND):
        self.path = path
        self.data = {
            "created_at": _now(),
            "max_spend_usd": max_spend,
            "steps": {},
            "spend": {"committed_usd": 0.0, "observed_usd": 0.0},
        }
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as fh:
                self.data = json.load(fh)
            self.data["max_spend_usd"] = max_spend

    # ── persistence ──────────────────────────────────────────────────────────

    def save(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(self.data, fh, indent=2)
        os.replace(tmp, self.path)     # atomic; a crash mid-write cannot corrupt
        return self.path

    # ── steps ────────────────────────────────────────────────────────────────

    def step(self, name):
        return self.data["steps"].get(name)

    def state(self, name):
        s = self.step(name)
        return s["state"] if s else "pending"

    def is_done(self, name):
        return self.state(name) == "scored"

    def mark(self, name, state, **fields):
        if state not in STATES:
            raise ValueError(f"unknown state {state!r}; expected one of {STATES}")
        entry = self.data["steps"].setdefault(name, {"name": name, "history": []})
        entry["state"] = state
        entry["updated_at"] = _now()
        entry.update(fields)
        entry["history"].append({"state": state, "at": entry["updated_at"]})
        self.save()
        return entry

    def reserve(self, name, projected_usd, n_requests):
        """Commit spend and mark the step BEFORE the provider call.

        check -> create -> commit has a crash window: if the provider accepts
        the request and this process dies before commit(), real money exists
        that the durable ledger has no record of, and crash recovery is exactly
        what G1 tests. So the reservation is persisted first and the batch id is
        attached afterwards. A reservation left dangling by a crash is
        conservatively counted as spent -- over-counting is recoverable, a lost
        submission is not.
        """
        self.data["spend"]["committed_usd"] += float(projected_usd)
        return self.mark(name, "submitted", batch_id=None, reserved=True,
                         n_requests=n_requests, projected_usd=projected_usd)

    def attach_batch(self, name, batch_id):
        """Record the provider id against an existing reservation."""
        return self.mark(name, "submitted", batch_id=batch_id, reserved=False)

    def release(self, name, projected_usd, reason=""):
        """The provider call failed, so give the reservation back."""
        self.data["spend"]["committed_usd"] -= float(projected_usd)
        return self.mark(name, "failed", reserved=False, error=reason)

    def dangling_reservations(self):
        """Steps holding a reservation with no batch id -- a crash left these.

        Each one is either a submission whose id was lost (money spent, results
        retrievable only by hand) or a create() that never landed. Both need a
        human, so they are surfaced rather than cleaned up automatically.
        """
        return [n for n, st in self.data["steps"].items()
                if st.get("state") == "submitted" and st.get("reserved")
                and not st.get("batch_id")]

    # ── spend ────────────────────────────────────────────────────────────────

    def commit(self, usd):
        """Reserve projected spend at submission time."""
        self.data["spend"]["committed_usd"] += float(usd)
        self.save()

    def observe(self, usd):
        """Record actual spend once usage comes back."""
        self.data["spend"]["observed_usd"] += float(usd)
        self.save()

    @property
    def committed(self):
        return self.data["spend"]["committed_usd"]

    @property
    def observed(self):
        return self.data["spend"]["observed_usd"]

    def projected_total(self, next_usd=0.0):
        """The larger of committed and observed, plus what is about to be spent.

        Using the max rather than only one of them means an underestimating
        projection cannot hide real spend, and an overestimating one cannot be
        quietly forgiven by a cheaper outturn.
        """
        return max(self.committed, self.observed) + float(next_usd)

    def check_spend(self, next_usd):
        """Consulted BEFORE submitting. Returns (allowed, message)."""
        cap = self.data["max_spend_usd"]
        projected = self.projected_total(next_usd)
        if projected <= cap:
            return True, (f"projected ${projected:.2f} of ${cap:.2f} cap "
                          f"(committed ${self.committed:.2f}, "
                          f"observed ${self.observed:.2f})")

        lines = [
            f"REFUSED: this submission would bring projected spend to "
            f"${projected:.2f}, over the ${cap:.2f} cap.",
            f"  already committed ${self.committed:.2f}, "
            f"observed ${self.observed:.2f}, this step ${float(next_usd):.2f}",
            "",
            "  Documented cut order (RUN_PLAN), apply in this sequence:",
        ]
        running = projected
        for name, saving, why in CUT_ORDER:
            running -= saving
            lines.append(f"    drop {name:<28} -${saving:>6.2f} "
                         f"-> ${running:>7.2f}   {why}")
            if running <= cap:
                lines.append(f"    ^ this alone brings the run under the cap")
                break
        return False, "\n".join(lines)

    # ── reporting ────────────────────────────────────────────────────────────

    def status(self):
        cap = self.data["max_spend_usd"]
        out = [f"ledger : {self.path}",
               f"spend  : committed ${self.committed:.2f}  "
               f"observed ${self.observed:.2f}  cap ${cap:.2f}"]
        if not self.data["steps"]:
            out.append("steps  : none recorded yet")
            return "\n".join(out)
        out.append(f"{'step':<28}{'state':<12}{'batch id':<28}{'usd':>8}")
        for name, s in self.data["steps"].items():
            out.append(f"{name:<28}{s.get('state','?'):<12}"
                       f"{str(s.get('batch_id') or '-'):<28}"
                       f"{s.get('projected_usd', 0.0):>8.2f}")
        pend = [n for n in self.data["steps"] if self.state(n) != "scored"]
        out.append(f"\nunfinished: {', '.join(pend) if pend else 'none'}")
        return "\n".join(out)


def parse_args():
    ap = argparse.ArgumentParser(description="Inspect or test the run ledger.")
    ap.add_argument("--path", default=DEFAULT_PATH)
    ap.add_argument("--max-spend", type=float, default=DEFAULT_MAX_SPEND)
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--check-spend", type=float, metavar="USD",
                    help="ask whether a submission of this size would be allowed")
    return ap.parse_args()


def main():
    a = parse_args()
    led = Ledger(a.path, a.max_spend)
    if a.check_spend is not None:
        ok, msg = led.check_spend(a.check_spend)
        print(msg)
        raise SystemExit(0 if ok else 1)
    print(led.status())


if __name__ == "__main__":
    main()
