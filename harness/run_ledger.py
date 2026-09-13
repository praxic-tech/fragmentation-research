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

# RUN_PLAN's tripwire, set deliberately rather than derived.
#
# The previous value was $170, justified as "above the $149.82 modelled
# ceiling". That justification is void: $149.82 predates medoid-of-k, repair
# retries and hierarchical pair scoring, so it is not a ceiling, it is an
# out-of-date estimate wearing a ceiling's clothes. A cap chosen as
# "the stale forecast plus headroom" is not a cap at all.
#
# $120 is a hard budget decision. It is deliberately allowed to sit BELOW
# whatever the regenerated cost model returns: if the forecast comes back
# higher, the correct outcome is a refusal and a cut from CUT_ORDER, not a
# larger number here. Raising it is a decision to spend more, made once,
# on purpose -- never a fix for a refused submission.
DEFAULT_MAX_SPEND = 120.00

# The wallet's actual floor. The tripwire above is a REFUSAL that forces a
# decision and can be raised deliberately with --max-spend; this cannot. A run
# configured above it is a configuration error, not a judgement call, so the
# Ledger refuses to construct itself rather than waiting to refuse a submission.
# Raised from $167 to $200 on 2026-09-13 by the user's budget decision
# (RUN_DECISIONS D9). The budget is OUT OF POCKET; once the sales-tax rate is
# known this becomes $200 / (1 + rate) in API credit.
HARD_LIMIT = 200.00

# Documented, in the order it should be applied. Not invented at the moment of
# refusal, when the temptation is to cut whatever is nearest.
#
# REBUILT for the joint run. The previous list priced cuts that no longer exist
# ("two granularity linkage cells" is an O+L concept) at figures from the
# superseded model, and offered "drop the clause row, -$31" computed at a 1.81x
# clause multiplier that RUN_PLAN had already measured at 1.31x. Under J the
# clause row is 4 x $3.63 and is a poor thing to cut.
#
# Ordered least-damaging first. Dollar figures track analysis/cost_model_v2.py
# at its selected settings; re-run the model rather than trusting these if the
# configuration changes.
CUT_ORDER = [
    ("repeats", 5.06, "reference cell x2; the variance bound is a "
                      "nice-to-have, not a claim"),
    ("J-vs-N curve", 1.67, "N = 1/3/5 on the reference cell; a secondary "
                           "figure, the grid still stands at N=7"),
    ("token-window row", 14.16, "3 cells; its 1.617 fragment multiplier is "
                                "the one granularity figure never independently "
                                "measured"),
    ("hierarchical arm, 46 of 71 pools", 17.94,
     "keeps the second attacker on 25 pools rather than losing it entirely"),
]

STATES = ("pending", "submitted", "fetched", "scored", "failed")


def _now():
    return datetime.now(timezone.utc).isoformat()


class Ledger:
    """One JSON file, written atomically, describing the whole run."""

    def __init__(self, path=DEFAULT_PATH, max_spend=DEFAULT_MAX_SPEND):
        if max_spend > HARD_LIMIT:
            raise ValueError(
                f"max_spend ${max_spend:.2f} is above the ${HARD_LIMIT:.2f} "
                "hard limit. The tripwire is a refusal you can raise on "
                "purpose; the hard limit is the wallet. Raising it is a "
                "decision to change the budget, made by editing HARD_LIMIT, "
                "never by passing a bigger --max-spend."
            )
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

    def settle(self, name, actual_usd):
        """Replace a finished step's worst-case reservation with what it cost.

        reserve() commits the WORST case -- every request running to its
        max_tokens -- because that is the only safe number before create().
        Leaving it there after the results are in means every completed wave
        keeps counting at its worst case forever. With max_tokens sized for real
        reasoning the worst case is roughly twice the actual, so the cap would
        refuse the run at about half its real spend. Once usage is known, the
        reservation is released and the actual cost committed and observed in
        its place. Idempotent: a resumed fetch settles a step once.
        """
        entry = self.data["steps"].get(name)
        if entry is None:
            raise KeyError(f"no ledger step {name!r} to settle")
        if entry.get("settled"):
            return entry
        reserved = float(entry.get("projected_usd") or 0.0)
        self.data["spend"]["committed_usd"] += float(actual_usd) - reserved
        self.data["spend"]["observed_usd"] += float(actual_usd)
        return self.mark(name, "fetched", settled=True, reserved=False,
                         actual_usd=float(actual_usd))

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

    def check_spend(self, next_usd, worst_usd=None):
        """Consulted BEFORE submitting. Returns (allowed, message).

        next_usd is what the tripwire sees. worst_usd, if given, is what the
        submission would cost if every request ran to its max_tokens; that is
        held against HARD_LIMIT, so the wallet cannot be breached even in the
        worst case, whatever the forecast says.
        """
        cap = self.data["max_spend_usd"]
        if worst_usd is not None:
            worst_total = self.projected_total(worst_usd)
            if worst_total > HARD_LIMIT:
                return False, (
                    f"REFUSED: if every request in this submission ran to its "
                    f"max_tokens, spend would reach ${worst_total:.2f}, over "
                    f"the ${HARD_LIMIT:.2f} hard limit (committed "
                    f"${self.committed:.2f}, this step's worst case "
                    f"${float(worst_usd):.2f}). Submit it in smaller waves.")
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
