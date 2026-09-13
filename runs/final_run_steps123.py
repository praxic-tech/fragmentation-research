"""
final_run_steps123.py — steps 1-3 of the approved final run (RUN_DECISIONS
D11/D12): headline J, grid J (4 waves) and identifier J. Approved by the user
2026-09-13 under the $197.64 credit hard wall with an $182 credit tripwire.

Per frozen spec, the protocol already decided (D4, D6):
    submit -> fetch -> resubmit transport holes ONCE -> ONE repair round
    (its own transport holes resubmitted once) -> harvest into the answer store
A call that exhausts 128k is a non-completion: never resubmitted, never
repaired. Across specs the phases run in order (D12): every base batch is
fetched, then EVERY resend completes, then the repair rounds start. Missing
experimental units come before repairs, so a credit shortfall can only cost
repairs. Then each game is scored with the same gate and report, into
results/final/<game>/REPORT.txt.

Base specs go out in spend order. More than one can be in flight; the ledger
refuses any submission past the tripwire or the hard wall, and a refused spec
is retried once earlier batches have settled. A batch already submitted is
fetched, never submitted again, so the script is resumable.

It STOPS after step 3. Headline O, grid O and the hierarchical attacker need a
re-forecast after grid J and the user's release.

    python runs/final_run_steps123.py --rehearse     # fake provider, temp dirs, $0
    python runs/final_run_steps123.py                # the real run
"""

import argparse
import contextlib
import hashlib
import io
import json
import os
import re
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
for d in ("adversaries", "harness", "analysis"):
    sys.path.insert(0, os.path.join(ROOT, d))

from answer_store import AnswerStore, harvest                      # noqa: E402
from batch_game import build_repair_spec, build_resubmit_spec, score  # noqa: E402
from batch_submit import (DEFAULT_STATE_DIR, IncompleteBatchError,   # noqa: E402
                          fetch, make_client, make_custom_id, read_state,
                          results_path, state_path, submit)
from run_ledger import DEFAULT_MAX_SPEND, Ledger                   # noqa: E402

GAMES = [("headlineJ", ["runs/final_headlineJ.json"]),
         ("gridJ", [f"runs/final_gridJ_w{k}.json" for k in (1, 2, 3, 4)]),
         ("identifierJ", ["runs/final_identifierJ.json"])]
SPEND_ORDER = ["runs/final_headlineJ.json", "runs/final_gridJ_w1.json", "runs/final_gridJ_w2.json",
               "runs/final_gridJ_w3.json", "runs/final_gridJ_w4.json", "runs/final_identifierJ.json"]


class CreditStop(RuntimeError):
    """The provider refused a submission for lack of credit. Stop cleanly."""


class Run:
    def __init__(self, client, state_dir, ledger, store, out_root, poll, log=print, manifest=None):
        self.client, self.state_dir, self.ledger = client, state_dir, ledger
        self.store, self.out_root, self.poll, self.log = store, out_root, poll, log
        self.files, self.repairs = {}, {}
        self.manifest = json.load(open(manifest, encoding="utf-8")) if manifest else None

    def _submit(self, spec):
        sp = state_path(self.state_dir, spec["tag"])
        if os.path.exists(sp):
            return read_state(sp)                   # resume: never pay twice
        try:
            return submit(spec, state_dir=self.state_dir, client=self.client, ledger=self.ledger)
        except Exception as err:                    # noqa: BLE001
            # The prepaid balance ran out mid-run on 2026-09-13 and this crashed
            # with a traceback. submit() already released the reservation when
            # create() failed, so stop cleanly and say how to resume.
            if "credit balance is too low" in str(err):
                raise CreditStop(f"{spec['tag']} refused: the account's credit balance is too low. "
                                 "Nothing was created or charged. Add credit, then re-run this script: "
                                 "submitted batches are fetched, never paid for twice.") from None
            raise

    def _complete(self, spec):
        """submit (if needed) + fetch; returns the results file."""
        state = self._submit(spec)
        res = fetch(state, state_dir=self.state_dir, client=self.client, wait=True,
                    poll_seconds=self.poll, ledger=self.ledger)
        self.log(f"  {spec['tag']}: {res['counts']}  actual ${res['actual_cost']:.4f}")
        return results_path(self.state_dir, spec["tag"])

    def _check_manifest(self, tag, rs):
        """A resend must be EXACTLY the committed manifest's entries for this
        batch, prompt hash for prompt hash. Anything else is refused."""
        if self.manifest is None:
            return
        want = {e["custom_id"]: e for e in self.manifest["resend"] if e["base_tag"] == tag}
        got = {make_custom_id(r["cell"], r["game"], r["unit"]): r for r in rs["requests"]}
        if set(got) != set(want):
            raise SystemExit(f"STOP: the resend for {tag} ({len(got)} requests) does not match the committed "
                             f"manifest ({len(want)} entries). Nothing was sent.")
        for cid, r in got.items():
            if hashlib.sha256(r["prompt"].encode("utf-8")).hexdigest() != want[cid]["resend_prompt_sha256"]:
                raise SystemExit(f"STOP: {cid}'s resent prompt does not match its manifest hash. Nothing was sent.")

    def resend_phase(self, path, spec, first_file):
        """The one unchanged retry of provider-refused / transport-failed units.
        Missing experimental units come before any repair (D12)."""
        files = [first_file]
        rs = build_resubmit_spec(spec, files, spec["tag"] + "-rs1")
        self._check_manifest(spec["tag"], rs)
        if rs["requests"]:
            self.log(f"  {spec['tag']}: resubmitting {len(rs['requests'])} transport holes once")
            files.append(self._complete(rs))
            harvest(self.store, rs, files)
        if rs.get("at_ceiling"):
            self.log(f"  {spec['tag']}: {len(rs['at_ceiling'])} non-completions at 128k (D6), not re-asked")
        harvest(self.store, spec, files)
        self.files[path] = files

    def repair_phase(self, path, spec):
        """The one repair round, for malformed / incomplete outputs only."""
        files = self.files[path]
        try:
            rp = build_repair_spec([(spec, files)], 1, 1, spec["tag"] + "-r1")
        except IncompleteBatchError as e:
            self.log(f"  {spec['tag']}: holes remain after resubmission; no repair round; the gate "
                     f"will refuse those cells ({str(e)[:80]})")
            return
        if rp["requests"]:
            self.log(f"  {spec['tag']}: repair round, {len(rp['requests'])} units")
            rfiles = [self._complete(rp)]
            rrs = build_resubmit_spec(rp, rfiles, rp["tag"] + "-rs1")
            if rrs["requests"]:
                rfiles.append(self._complete(rrs))
            harvest(self.store, rp, rfiles)
            self.repairs[path] = (rp, rfiles)

    def run(self):
        specs = {p: json.load(open(p, encoding="utf-8")) for p in SPEND_ORDER}
        states, waiting = {}, list(SPEND_ORDER)

        def submit_what_fits():
            while waiting:
                try:
                    states[waiting[0]] = self._submit(specs[waiting[0]])
                except SystemExit as refusal:       # tripwire / hard wall: wait for settles
                    self.log(f"  ledger holds {specs[waiting[0]]['tag']} until earlier batches settle: "
                             f"{str(refusal).splitlines()[0][:90]}")
                    return
                waiting.pop(0)

        submit_what_fits()
        firsts = {}
        for path in SPEND_ORDER:
            if path not in states:
                submit_what_fits()
            if path not in states:
                raise SystemExit(f"STOP: {specs[path]['tag']} cannot be submitted within the ledger's "
                                 "limits even with nothing in flight. Re-forecast before going on.")
            firsts[path] = self._complete(specs[path])
            submit_what_fits()
        # Missing experimental units before repairs (D12): every resend of a
        # provider-refused or transport-failed unit is completed before any
        # repair request is sent, so a shortfall can only cost repairs.
        for path in SPEND_ORDER:
            self.resend_phase(path, specs[path], firsts[path])
        for path in SPEND_ORDER:
            self.repair_phase(path, specs[path])

        for game, paths in GAMES:
            base = [specs[p] for p in paths]
            combined = {**base[0], "build": {**base[0]["build"],
                                             "pools": [pl for s in base for pl in s["build"]["pools"]]},
                        "requests": [r for s in base for r in s["requests"]],
                        "sidecar": {c: v for s in base for c, v in s["sidecar"].items()}}
            waves = [(combined, [f for p in paths for f in self.files[p]])]
            waves += [self.repairs[p] for p in paths if p in self.repairs]
            out = os.path.join(self.out_root, game)
            buf = io.StringIO()
            try:
                with contextlib.redirect_stdout(buf):
                    verdict = score(waves, out)
                refused = sorted(c for c, v in verdict.items() if v)
            except IncompleteBatchError as e:
                refused = [f"not scored: {e}"]
            os.makedirs(out, exist_ok=True)
            open(os.path.join(out, "REPORT.txt"), "w", encoding="utf-8").write(buf.getvalue())
            self.log(f"{game}: scored -> {out}/REPORT.txt; refused: {refused or 'none'}")
        self.log(f"steps 1-3 done. ledger: observed ${self.ledger.observed:.2f}, "
                 f"committed ${self.ledger.committed:.2f}. STOP -- re-forecast before steps 4-6.")


# ── rehearsal: a fake provider, temp directories, no money ─────────────────
class _O:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class _FakeBatches:
    def __init__(self):
        self.store, self.n, self.seen = {}, 0, 0

    def create(self, requests):
        self.n += 1
        self.store[f"fb{self.n}"] = list(requests)
        return _O(id=f"fb{self.n}")

    def retrieve(self, bid):
        return _O(processing_status="ended")

    def results(self, bid):
        for req in self.store[bid]:
            self.seen += 1
            prompt = req["params"]["messages"][0]["content"]
            labels = re.findall(r"^(m_\d{7}|[a-z]+_\d+(?:_frag_\d+)?): ", prompt, re.M)
            n = int(re.search(r"from (\d+) different records", prompt).group(1))
            if self.seen in (3, 60):                # transport holes, in headline and grid w1
                yield _O(custom_id=req["custom_id"], result=_O(type="errored", error="overloaded"))
                continue
            text = "no list here" if self.seen == 5 else json.dumps([labels[i::n] for i in range(n)])
            if self.seen == 7:                      # a non-completion at the ceiling
                msg = _O(content=[_O(type="text", text="")], stop_reason="max_tokens",
                         usage=_O(input_tokens=100, output_tokens=128000))
            else:
                msg = _O(content=[_O(type="text", text=text)], stop_reason="end_turn",
                         usage=_O(input_tokens=100, output_tokens=80))
            yield _O(custom_id=req["custom_id"], result=_O(type="succeeded", message=msg))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rehearse", action="store_true")
    a = ap.parse_args()
    if a.rehearse:
        tmp = tempfile.mkdtemp(prefix="final_rehearse_")
        try:
            client = _O(messages=_O(batches=_FakeBatches()))
            led = Ledger(os.path.join(tmp, "ledger.json"), max_spend=DEFAULT_MAX_SPEND)
            Run(client, os.path.join(tmp, "batches"), led, AnswerStore(os.path.join(tmp, "store.jsonl")),
                os.path.join(tmp, "final"), poll=0).run()
            reports = [os.path.exists(os.path.join(tmp, "final", g, "REPORT.txt")) for g, _ in GAMES]
            steps = led.data["steps"]
            order = list(steps)                     # the ledger records batches in submission order
            resends = [i for i, t in enumerate(order) if t.endswith("-rs1") and "-r1" not in t]
            repairs = [i for i, t in enumerate(order) if "-r1" in t]
            first = len(resends) >= 2 and bool(repairs) and max(resends) < min(repairs)
            print(f"REHEARSAL: {len(steps)} batches, every one settled: "
                  f"{all(s.get('settled') for s in steps.values())}; reports written: {all(reports)}")
            print(f"  submission order: {order}")
            print(f"  all {len(resends)} resend batches before all {len(repairs)} repair batches: {first}")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        return
    try:
        Run(make_client(), DEFAULT_STATE_DIR, Ledger(max_spend=DEFAULT_MAX_SPEND), AnswerStore(),
            os.path.join("results", "final"), poll=60,
            manifest="runs/resend_manifest_2026-09-13.json").run()
    except CreditStop as stop:
        print(f"\nSTOPPED CLEANLY: {stop}")
        sys.exit(2)


if __name__ == "__main__":
    main()
