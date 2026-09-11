"""
test_hier_batch.py — gate G2c: the batch hierarchical attacker is the same attacker.

adversaries/hier_batch.py runs hierarchical.attack() in waves by replay: each
wave replays the attack from cached answers and turns the pairs it still needs
into a Batches request. The claim is that this asks exactly the interactive
attacker's questions and reaches exactly its answer. Checked here against a
pair oracle built from the answer key, with no API calls:

    equivalence   batch waves reproduce offline attack() exactly
    wire format   every wave spec passes batch_submit.build_requests
    transport     an errored batch is asked once more, then given up
    exhausted     a batch that used the whole 128k is never re-asked (D6)
    holes         a pool past HOLE_CAP unanswered is refused, not scored
    idempotence   the same wave cannot be ingested twice

Run:  python harness/test_hier_batch.py
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
sys.path.insert(0, os.path.join(ROOT, "analysis"))

from batch_submit import build_requests, reset_preflight_stats   # noqa: E402
from cost_model_v2 import MODEL_MAX_OUTPUT                        # noqa: E402
from hier_batch import (DEFAULT_K, HOLE_CAP, ingest, plan,        # noqa: E402
                        pool_units, score)
from hierarchical import attack, score_pairs_offline              # noqa: E402
from joint_game import build_units                                # noqa: E402

CELL = os.path.join(ROOT, "results", "o_probe", "random__sentence")
SEED = 42
_failures = []


def check(name, cond, detail=""):
    if not cond:
        _failures.append(name)
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}{('  — ' + detail) if detail else ''}")


def the_pool():
    _o, units, _key, _truth = build_units(CELL, 8, 7, SEED)
    rids = sorted({f["record_id"] for f in units[0][1]})[:4]
    return [("pool_t", rids)]


def oracle_for(pools):
    """(same, p_i_before_j) from the answer key, keyed by masked label."""
    _o, _u, _key, truth = build_units(CELL, 0, 7, SEED, pools=pools, o_docs=[])
    (pid, _masked, id_map, _n), = pool_units(CELL, pools, SEED)
    where = {fid: (rid, k) for rid, order in truth[pid].items() for k, fid in enumerate(order)}
    lab = {label: where[fid] for label, fid in id_map.items()}

    def oracle(i, j):
        (ri, pi), (rj, pj) = lab[i], lab[j]
        return (1.0, 1.0 if pi < pj else 0.0) if ri == rj else (0.0, 0.5)
    return oracle


def answer_rows(spec, oracle, faults=None, keep=None):
    """What a perfect model would return for every pair batch in the wave.
    keep(i, j) False = the model leaves that pair out of its answer."""
    faults = faults or {}
    rows = []
    for cid, s in spec["sidecar"].items():
        kind = faults.get(cid)
        if kind == "errored":
            rows.append({"custom_id": cid, "result_type": "errored", "error": "overloaded"})
            continue
        if kind == "exhausted":
            rows.append({"custom_id": cid, "result_type": "succeeded", "stop_reason": "max_tokens",
                         "error": "TruncatedAnswerError",
                         "usage": {"input_tokens": 100, "output_tokens": MODEL_MAX_OUTPUT}})
            continue
        ans = []
        for pid, (i, j, flip) in s["pairs"].items():
            if keep is not None and not keep(i, j):
                continue
            same, p = oracle(i, j)
            ans.append({"pair_id": int(pid), "same": same, "before": (1.0 - p) if flip else p})
        rows.append({"custom_id": cid, "result_type": "succeeded", "stop_reason": "end_turn",
                     "text": json.dumps(ans), "usage": {"input_tokens": 100, "output_tokens": 50}})
    return rows


def write(path, rows):
    with io.open(path, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    return path


def run_waves(pools, oracle, out_root, tmp, tag, faults_by_wave=None, max_waves=8, keep=None,
              k=DEFAULT_K):
    specs = []
    for wave in range(max_waves):
        spec = plan([CELL], pools, wave, f"{tag}-w{wave}", out_root, seed=SEED, k=k)
        specs.append(spec)
        if not spec["requests"]:
            break
        faults = (faults_by_wave or {}).get(wave, lambda s: {})(spec)
        f = write(os.path.join(tmp, f"{tag}-w{wave}.jsonl"),
                  answer_rows(spec, oracle, faults, keep=keep))
        ingest(spec, [f])
    return specs


def main():
    print("=" * 70)
    print(" G2c — the batch hierarchical attacker is the same attacker")
    print("=" * 70)
    tmp = tempfile.mkdtemp(prefix="g2c_")
    try:
        _run(tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("\n" + "=" * 70)
    if _failures:
        print(f" FAILED — {len(_failures)}: {', '.join(_failures)}")
        raise SystemExit(1)
    print(" G2c PASSED")
    print("=" * 70)


def _run(tmp):
    pools = the_pool()
    oracle = oracle_for(pools)
    (pid, masked, _id_map, n), = pool_units(CELL, pools, SEED)

    print("\nequivalence with the offline attacker")
    ref_groups, ref_tel = attack(masked, n, lambda pairs: score_pairs_offline(pairs, oracle, seed=SEED),
                                 k=DEFAULT_K, seed=SEED)
    out = os.path.join(tmp, "clean")
    specs = run_waves(pools, oracle, out, tmp, "clean")
    check("the waves run to completion", not specs[-1]["requests"] and specs[-1]["done"],
          f"{len(specs) - 1} wave(s) of pair batches")
    from hier_batch import PairCache, replay
    cache = PairCache(os.path.join(out, os.path.basename(CELL), pid, "pairs.jsonl"))
    (groups, tel), _ = replay(pool_units(CELL, pools, SEED)[0], cache, SEED, DEFAULT_K, 20)
    check("batch waves reproduce offline attack() EXACTLY", groups == ref_groups,
          f"{len(groups)} groups, {sum(map(len, groups))} fragments")
    check("the same bridge rounds were taken", tel["bridge_rounds"] == ref_tel["bridge_rounds"],
          f"{tel['bridge_rounds']} bridge round(s)")
    check("pair prompts carry no labels, only text",
          all("m_0" not in r["prompt"] for s in specs for r in s["requests"]))
    reset_preflight_stats()
    reqs = build_requests(specs[0])
    check("a wave spec passes the real submission builder (game H, 128k)",
          len(reqs) == len(specs[0]["requests"])
          and all(r["params"]["max_tokens"] == MODEL_MAX_OUTPUT for r in reqs),
          f"{len(reqs)} requests, e.g. {reqs[0]['custom_id']}")
    verdict = score([CELL], pools, out, seed=SEED)
    check("the perfect-oracle pool scores through the same gate", not verdict[os.path.basename(CELL)])
    try:
        ingest(specs[0], [os.path.join(tmp, "clean-w0.jsonl")])
        check("the same wave cannot be ingested twice", False, "it was")
    except ValueError:
        check("the same wave cannot be ingested twice", True)

    print("\nequivalence when clustering needs BRIDGE rounds (multi-wave replay)")
    # The clusterer asks for bridges when the graph of OBSERVED pairs has more
    # than N components, and every answered pair is an edge whatever its
    # `same`. So bridges come from pairs going UNANSWERED: the fake model
    # answers only same-record neighbours and omits every other pair; the
    # offline reference drops exactly the same pairs.
    _o, _u, _k, truth = build_units(CELL, 0, 7, SEED, pools=pools, o_docs=[])
    where = {fid: (rid, kk) for rid, order in truth[pid].items() for kk, fid in enumerate(order)}
    lab = {label: where[fid] for label, fid in _id_map.items()}

    def keep(i, j):
        (ri, pi), (rj, pj) = lab[i], lab[j]
        return ri == rj and abs(pi - pj) == 1

    def offline_dropping(pairs):
        return score_pairs_offline([p for p in pairs if keep(*p)], oracle, seed=SEED)
    ref_g2, ref_t2 = attack(masked, n, offline_dropping, k=DEFAULT_K, seed=SEED)
    out5 = os.path.join(tmp, "bridges")
    specs5 = run_waves(pools, oracle, out5, tmp, "br", keep=keep)
    cache5 = PairCache(os.path.join(out5, os.path.basename(CELL), pid, "pairs.jsonl"))
    (g2, t2), _ = replay(pool_units(CELL, pools, SEED)[0], cache5, SEED, DEFAULT_K, 20)
    check("dropping pairs forces bridge rounds offline", ref_t2["bridge_rounds"] >= 1,
          f"{ref_t2['bridge_rounds']} bridge round(s)")
    check("a pair left unanswered is NOT re-asked when a bridge round proposes it "
          "again (batch rule; one wave)", len(specs5) - 1 == 1, f"{len(specs5) - 1} wave(s)")
    check("and the result still equals the offline attacker EXACTLY",
          g2 == ref_g2 and t2["bridge_rounds"] == ref_t2["bridge_rounds"],
          f"{len(g2)} groups, {t2['bridge_rounds']} bridge round(s)")

    print("\nequivalence when bridge rounds ask NEW pairs (k = 1: a disconnected candidate graph)")
    ref_g3, ref_t3 = attack(masked, n, lambda pairs: score_pairs_offline(pairs, oracle, seed=SEED),
                            k=1, seed=SEED)
    out6 = os.path.join(tmp, "k1")
    specs6 = run_waves(pools, oracle, out6, tmp, "k1", k=1)
    cache6 = PairCache(os.path.join(out6, os.path.basename(CELL), pid, "pairs.jsonl"))
    (g3, t3), _ = replay(pool_units(CELL, pools, SEED)[0], cache6, SEED, 1, 20)
    check("k = 1 forces bridge rounds offline", ref_t3["bridge_rounds"] >= 1,
          f"{ref_t3['bridge_rounds']} bridge round(s)")
    check("each new bridge round is its own wave",
          len(specs6) - 1 == 1 + ref_t3["bridge_rounds"], f"{len(specs6) - 1} waves")
    check("multi-wave replay reproduces offline attack() EXACTLY",
          g3 == ref_g3 and t3["bridge_rounds"] == ref_t3["bridge_rounds"],
          f"{len(g3)} groups over {len(specs6) - 1} waves")

    print("\ntransport: asked once more, then given up")
    out2 = os.path.join(tmp, "transport")
    first = {}
    def err_first(spec):
        cid = sorted(spec["sidecar"])[0]
        first["cid"], first["pairs"] = cid, spec["sidecar"][cid]["pairs"]
        return {cid: "errored"}
    s0 = plan([CELL], pools, 0, "tr-w0", out2, seed=SEED)
    ingest(s0, [write(os.path.join(tmp, "tr0.jsonl"), answer_rows(s0, oracle, err_first(s0)))])
    s1 = plan([CELL], pools, 1, "tr-w1", out2, seed=SEED)
    again = [s for s in s1["sidecar"].values() if s["pairs"] == first["pairs"]]
    check("an errored batch is asked again, unchanged, in the next wave", len(again) == 1)
    ingest(s1, [write(os.path.join(tmp, "tr1.jsonl"),
                      answer_rows(s1, oracle, {again[0]["custom_id"]: "errored"}))])
    s2 = plan([CELL], pools, 2, "tr-w2", out2, seed=SEED)
    check("a second failure gives its pairs up: not asked a third time",
          not any(s["pairs"] == first["pairs"] for s in s2["sidecar"].values()))

    print("\nD6: a batch that exhausts 128k is never re-asked")
    out3 = os.path.join(tmp, "ceiling")
    t0 = plan([CELL], pools, 0, "ce-w0", out3, seed=SEED)
    cid = sorted(t0["sidecar"])[0]
    lost = t0["sidecar"][cid]["pairs"]
    ingest(t0, [write(os.path.join(tmp, "ce0.jsonl"), answer_rows(t0, oracle, {cid: "exhausted"}))])
    t1 = plan([CELL], pools, 1, "ce-w1", out3, seed=SEED)
    check("its pairs are recorded unanswered and not re-planned",
          not any(s["pairs"] == lost for s in t1["sidecar"].values()))

    print("\nholes: past HOLE_CAP the pool is refused")
    out4 = os.path.join(tmp, "holes")
    specs4 = run_waves(pools, oracle, out4, tmp, "ho",
                       faults_by_wave={0: lambda spec: {c: "exhausted" for c in spec["sidecar"]}})
    v = score([CELL], pools, out4, seed=SEED)
    check(f"a pool with every pair unanswered (> {HOLE_CAP:.0%}) is refused, not scored",
          v[os.path.basename(CELL)] == {"J"}, str(v))


if __name__ == "__main__":
    main()
