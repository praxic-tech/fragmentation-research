"""
test_batch_rehearsal.py — gate G1: the whole PAID path, end to end, for $0.

The free-tier runs exercise joint_game. The paid run does not use joint_game's
loop at all -- it goes spec -> Batches API -> fetch -> resubmit -> repair wave ->
score -- and until this existed, most of that path had never run once. It could
not have: nothing turned a batch answer back into a score, the spec builder
threw the alias maps away, max_tokens was sized for the bare answer rather than
the reasoning, and the ledger never settled a wave.

A fake Anthropic client stands in for the provider. It answers PERFECTLY unless
told to fault, so the end-to-end identity check is sharp: a perfect attacker
must come back scoring exactly 1.0 through the whole bridge, or the bridge is
mis-mapping labels. Faults injected, each of which has to be survived:

    kill mid-fetch        resume loses nothing and duplicates nothing
    errored / expired     a transport hole: the wave is REFUSED until resubmitted
    empty (all reasoning) likewise
    garbage text          not an answer: repair round resends the original prompt
    incomplete answer     repair round with bookkeeping-only feedback
    never answers         after the round budget the unit is not written and its
                          cell is REFUSED -- never scored from the fill-in policy

Plus the ledger: worst case reserved before create(), settled to actual after
fetch, so completed waves stop counting at their worst case.

Run:  python harness/test_batch_rehearsal.py
"""

import io
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "adversaries"))

from batch_game import (build_repair_spec, build_resubmit_spec, build_spec,
                        score)
from batch_submit import (IncompleteBatchError, fetch, results_path,
                          submit)
from joint_game import build_units, score_row
from run_ledger import Ledger

_failures = []


def check(name, cond, detail=""):
    if not cond:
        _failures.append(name)
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}{('  — ' + detail) if detail else ''}")


# ── the fake provider ────────────────────────────────────────────────────────

class _Obj:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class FakeBatches:
    """messages.batches with the three calls batch_submit makes."""

    def __init__(self, responder):
        self.responder = responder
        self.store = {}
        self.n = 0
        self.die_after = None          # set to k: the next results() drops at k

    def create(self, requests):
        self.n += 1
        bid = f"fakebatch_{self.n:03d}"
        self.store[bid] = list(requests)
        return _Obj(id=bid, processing_status="in_progress")

    def retrieve(self, bid):
        return _Obj(id=bid, processing_status="ended")

    def results(self, bid):
        for i, req in enumerate(self.store[bid]):
            if self.die_after is not None and i == self.die_after:
                self.die_after = None
                raise ConnectionError("simulated connection drop mid-fetch")
            yield self.responder(req)


class FakeClient:
    def __init__(self, responder):
        self.batches = FakeBatches(responder)
        self.messages = _Obj(batches=self.batches)


def _ok(cid, text, prompt):
    msg = _Obj(content=[_Obj(type="text", text=text)],
               usage=_Obj(input_tokens=len(prompt) // 4, output_tokens=60))
    return _Obj(custom_id=cid, result=_Obj(type="succeeded", message=msg))


def _fail(cid, kind):
    return _Obj(custom_id=cid, result=_Obj(type=kind, error=f"{kind}_error"))


# ── a perfect attacker, driven by the answer key ─────────────────────────────

class Oracle:
    """Answers every request correctly in masked labels, unless a fault says not."""

    def __init__(self, build):
        self.side = {}
        self.truth = {}
        self.build = build
        self.faults = {}               # (base_cid, round) -> kind

    def learn(self, spec):
        self.side.update(spec["sidecar"])

    def _truth(self, cell_dir):
        if cell_dir not in self.truth:
            _, _, key, pool_truth = build_units(
                os.path.join(ROOT, cell_dir), self.build["docs"],
                self.build["pool_size"], self.build["seed"])
            self.truth[cell_dir] = (key, pool_truth)
        return self.truth[cell_dir]

    def answer(self, s):
        key, pool_truth = self._truth(s["cell_dir"])
        inv = {fid: lab for lab, fid in s["alias_map"].items()}
        if s["game"] == "O":
            return [inv[f] for f in key[s["unit"]]]
        return [[inv[f] for f in order] for order in pool_truth[s["unit"]].values()]

    def __call__(self, req):
        cid = req["custom_id"]
        s = self.side[cid]
        prompt = req["params"]["messages"][0]["content"]
        key = (s["base_cid"], s["round"])
        kind = self.faults.get(key)
        if kind in ("errored", "expired", "canceled", "empty"):
            # Transport faults are TRANSIENT: a resubmission is a fresh attempt.
            # (Keyed as permanent, the fake failed every resubmission too, and
            # the product correctly refused to score -- a test bug, not a
            # product one, but the persistent case is covered by the refusal.)
            del self.faults[key]
            if kind == "empty":
                return _ok(cid, "", prompt)
            return _fail(cid, kind)
        if kind == "garbage":
            return _ok(cid, "I would put the clinical history first, roughly.",
                       prompt)
        ans = self.answer(s)
        if kind == "drop2":
            ans = [list(g) for g in ans]
            ans[0] = ans[0][2:]
        return _ok(cid, json.dumps(ans), prompt)


# ── the rehearsal ────────────────────────────────────────────────────────────

CELLS = [os.path.join(ROOT, "results", "o_probe", "random__sentence"),
         os.path.join(ROOT, "results", "o_probe", "llm-cut__llm-decides")]


def run_wave(client, oracle, spec, state_dir, led, die_after=None):
    oracle.learn(spec)
    state = submit(spec, state_dir=state_dir, client=client, ledger=led)
    if die_after is not None:
        client.batches.die_after = die_after
        try:
            fetch(state, state_dir=state_dir, client=client, ledger=led)
        except ConnectionError:
            pass
    return state, fetch(state, state_dir=state_dir, client=client, ledger=led)


def rehearse():
    tmp = tempfile.mkdtemp(prefix="g1_")
    try:
        _rehearse(tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _rehearse(tmp):
    state_dir = os.path.join(tmp, "batches")
    led = Ledger(os.path.join(tmp, "ledger.json"), max_spend=120.0)

    print("\nbuild: prompts, alias maps and max_tokens")
    spec0 = build_spec(CELLS, ["J", "O"], docs=8, pool_size=7, seed=42,
                       tag="g1-w0")
    side = spec0["sidecar"]
    check("every request carries its alias map in the sidecar",
          all(len(s["alias_map"]) == s["n_fragments"] for s in side.values()),
          f"{len(side)} requests")
    big_j = max((s for s in side.values() if s["game"] == "J"),
                key=lambda s: s["n_fragments"])
    check("max_tokens for a 7-document J pool is far above the old 8,192 cap",
          big_j["max_tokens"] > 8192,
          f"{big_j['n_fragments']} fragments -> max_tokens {big_j['max_tokens']:,}")

    oracle = Oracle(spec0["build"])
    client = FakeClient(oracle)
    o_units = sorted(c for c, s in side.items() if s["game"] == "O")
    j_units = sorted(c for c, s in side.items() if s["game"] == "J")
    for c, kind in ((o_units[0], "errored"), (o_units[1], "expired"),
                    (o_units[2], "empty"), (o_units[3], "garbage"),
                    (j_units[0], "drop2")):
        oracle.faults[(c, 0)] = kind
    never = o_units[4]
    for rnd in range(0, 4):
        oracle.faults[(never, rnd)] = "garbage"

    print("\nwave 0: submit, killed mid-fetch, resumed")
    committed_before = led.committed
    state0, res0 = run_wave(client, oracle, spec0, state_dir, led, die_after=5)
    r0 = results_path(state_dir, "g1-w0")
    lines = [json.loads(l) for l in io.open(r0, encoding="utf-8") if l.strip()]
    check("resume after a mid-fetch drop loses nothing and duplicates nothing",
          len(lines) == len(side) and len({l["custom_id"] for l in lines}) == len(side),
          f"{len(lines)} rows for {len(side)} requests")
    check("an errored / expired / empty wave is reported INCOMPLETE",
          not res0["complete"] and len(res0["unanswered"]) == 3,
          f"unanswered {len(res0['unanswered'])}")
    check("the ledger settled the finished wave to its actual cost",
          res0["settled"] and led.committed < committed_before + 1e-9 + led.committed
          and abs(led.committed - res0["actual_cost"]) < 1e-9,
          f"committed ${led.committed:.4f} = actual ${res0['actual_cost']:.4f}")

    try:
        score([(spec0, [r0])], os.path.join(tmp, "scored"))
        check("scoring refuses a wave with holes in it", False, "it scored")
    except IncompleteBatchError as e:
        check("scoring refuses a wave with holes in it", True, str(e)[:60] + "...")

    print("\nresubmit: the transport holes only, unchanged")
    rs = build_resubmit_spec(spec0, [r0], "g1-w0-rs1")
    check("exactly the errored, expired and empty requests are resubmitted",
          len(rs["requests"]) == 3, f"{len(rs['requests'])} requests")
    _, res_rs = run_wave(client, oracle, rs, state_dir, led)
    r0rs = results_path(state_dir, "g1-w0-rs1")
    wave0 = (spec0, [r0, r0rs])

    print("\nrepair wave 1")
    sp1 = build_repair_spec([wave0], round_no=1, max_rounds=2, tag="g1-w1")
    by_base = {s["base_cid"]: s for s in sp1["sidecar"].values()}
    check("repair asks exactly the garbage, incomplete and never-answering units",
          set(by_base) == {o_units[3], j_units[0], never},
          f"{len(by_base)} units")
    g = by_base[o_units[3]]
    check("an unparseable answer gets the ORIGINAL prompt back, not a correction",
          g["prompt_sent"] == g["prompt"])
    d = by_base[j_units[0]]
    fb = d["prompt_sent"][len(d["prompt"]):].lower()
    check("an incomplete answer gets bookkeeping feedback, and no ground truth",
          "absent from your answer" in fb
          and not any(w in fb for w in ("belongs", "same record", "adjacent")),
          fb.strip()[:60] + "...")
    _, _ = run_wave(client, oracle, sp1, state_dir, led)
    r1 = results_path(state_dir, "g1-w1")

    sp2 = build_repair_spec([wave0, (sp1, [r1])], round_no=2, max_rounds=2,
                            tag="g1-w2")
    check("round 2 only re-asks what is still broken",
          {s["base_cid"] for s in sp2["sidecar"].values()} == {never})
    _, _ = run_wave(client, oracle, sp2, state_dir, led)
    r2 = results_path(state_dir, "g1-w2")
    sp3 = build_repair_spec([wave0, (sp1, [r1]), (sp2, [r2])], round_no=3,
                            max_rounds=2, tag="g1-w3")
    check("the round budget is respected", not sp3["requests"])

    print("\nscore: the same gate and scorer as the interactive path")
    out_root = os.path.join(tmp, "scored")
    waves = [wave0, (sp1, [r1]), (sp2, [r2])]
    verdict = score(waves, out_root)
    cell_never = spec0["sidecar"][never]["cell"]
    check("the cell holding a never-answering unit is REFUSED",
          verdict[cell_never] == {"O"}, f"{cell_never}: {sorted(verdict[cell_never])}")
    others = {c: v for c, v in verdict.items() if c != cell_never}
    check("every other cell passes the integrity gate",
          all(not v for v in others.values()), str(others))

    print("\nidentity: a perfect attacker must score exactly 1.0 end to end")
    for cell_dir in CELLS:
        cell = os.path.basename(cell_dir)
        _, _, key, pool_truth = build_units(cell_dir, 8, 7, 42)
        rows = {}
        for g in ("O", "J"):
            p = os.path.join(out_root, cell, f"{g}.jsonl")
            rows[g] = [score_row(json.loads(l), key, pool_truth)
                       for l in io.open(p, encoding="utf-8") if l.strip()]
        taus = [r["tau"] for r in rows["O"] if not r.get("malformed")]
        j1 = [r["joint_f1"] for r in rows["J"]]
        check(f"{cell}: every O document at tau 1.0, every J pool at F1 1.0",
              taus and j1 and all(abs(t - 1) < 1e-9 for t in taus)
              and all(abs(x - 1) < 1e-9 for x in j1),
              f"{len(taus)} O docs, {len(j1)} J pools")
    written = [json.loads(l) for l in io.open(
        os.path.join(out_root, cell_never, "O.jsonl"), encoding="utf-8") if l.strip()]
    check("the never-answering unit was never written -- not a fabricated row",
          spec0["sidecar"][never]["unit"] not in {w["unit"] for w in written})

    print("\nledger across the whole rehearsal")
    steps = led.data["steps"]
    check("every wave settled; nothing still counts at its worst case",
          all(st.get("settled") for st in steps.values()),
          f"{len(steps)} waves, committed ${led.committed:.4f}")

    print("\nG3 positive control: the unmasked arm is scoreable and near-perfect")
    ctrl = build_spec(CELLS[:1], ["J"], docs=8, pool_size=7, seed=42,
                      tag="g1-ctrl", arm="unmasked", control=True)
    check("unmasked requests are flagged, never silently unmasked",
          all(r.get("unmasked_control") for r in ctrl["requests"]))
    oracle.learn(ctrl)
    _, _ = run_wave(client, oracle, ctrl, state_dir, led)
    rc = results_path(state_dir, "g1-ctrl")
    v = score([(ctrl, [rc])], os.path.join(tmp, "ctrl"))
    cc = ctrl["requests"][0]["cell"]
    _, _, key, pool_truth = build_units(CELLS[0], 8, 7, 42)
    j1 = [score_row(json.loads(l), key, pool_truth)["joint_f1"]
          for l in io.open(os.path.join(tmp, "ctrl", cc, "J.jsonl"),
                           encoding="utf-8") if l.strip()]
    check("the unmasked control scores 1.0 through the same bridge",
          not v[cc] and j1 and all(abs(x - 1) < 1e-9 for x in j1),
          f"{len(j1)} pools")


def main():
    print("=" * 70)
    print(" G1 — the paid path, end to end, against a fake provider ($0)")
    print("=" * 70)
    rehearse()
    print("\n" + "=" * 70)
    if _failures:
        print(f" FAILED — {len(_failures)}: {', '.join(_failures)}")
        raise SystemExit(1)
    print(" G1 PASSED")
    print("=" * 70)


if __name__ == "__main__":
    main()
