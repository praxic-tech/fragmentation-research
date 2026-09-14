"""
embedding_smoke.py — the SCORE-BLIND development smoke test for the post-hoc
exploratory embedding adversary (RUN_DECISIONS D14). No API calls.

Development material only:
  grid pool 1 (pool_000, screening) in all nine retained cells, and
  identifier records r_0000..r_0048 (excluded from the final sample) dealt
  into 7 pools of 7.
No final, grid pool 2-25 or headline pool is read. NO RECONSTRUCTION SCORE IS
COMPUTED OR PRINTED; the outputs are checked for validity only.

Checks:
  0  model files match the D14 pins (SHA-256 / git blob ids)
  1  pipeline runs end to end
  2  actual word-piece lengths and truncation at the model limit
  3  embedding reproducibility (same inputs twice)
  4  batch-size numerical stability (1 / 16 / 64 / 128) and cluster agreement
  5  clustering / scorer compatibility: a valid partition, exactly N groups,
     every id once (validity only)
  6  determinism across processes (PYTHONHASHSEED 0 vs 1)
  7  the grouper equals memon_joint.group_known_n when given TF-IDF similarity
  8  CPU throughput, and a measured projection for the 62,527 final fragments

    python runs/embedding_smoke.py
"""

import hashlib
import json
import os
import subprocess
import sys
import time
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
for d in ("adversaries", "harness", "analysis"):
    sys.path.insert(0, os.path.join(ROOT, d))

import numpy as np                                                   # noqa: E402

import embedding_joint as EJ                                         # noqa: E402
from batch_game import load_frame                                    # noqa: E402
from joint_game import _unit_seed, build_units                       # noqa: E402

OUT = "results/audit/embedding_smoke"
FINAL_FRAGMENTS, FINAL_POOLS = 62_527, 282
CELLS = ["random__sentence", "random__clause", "random__token-window", "semantic__sentence", "semantic__clause",
         "coherence-sever__clause", "coherence-sever__token-window", "subject-verb__sentence", "subject-verb__clause"]
PINS = {"model.safetensors": ("sha256", "78c0197b6159d92658e319bc1d72e4c73a9a03dd03815e70e555c5ef05615658"),
        "tokenizer.json": ("blob", "7c8e194053bc80e27e19bb2125469e4f289ab2b3"),
        "vocab.txt": ("blob", "1c51ab79a2298a340952d3e6012042a9c84bbe4d"),
        "config.json": ("blob", "b9fd4298819da011007a6a4ceb728c860914fc88"),
        "modules.json": ("blob", "952a9b81c0bfd99800fabf352f69c7ccd46c5e43"),
        "1_Pooling/config.json": ("blob", "4e09f293dfe90bba49f87cfe7996271f07be2666"),
        "sentence_bert_config.json": ("blob", "4eb670bb4e7f34e9031acec2b86d39e5c921198e"),
        "config_sentence_transformers.json": ("blob", "fd1b291129c607e5d49799f87cb219b27f98acdf"),
        "special_tokens_map.json": ("blob", "378d4fa393d5eaccf69c437a20f1cda6ac65c14d"),
        "tokenizer_config.json": ("blob", "20ae1276042f43d1c80f4f7b7f084a8704592c1d")}


def dev_units():
    """[(unit_id, fragments, n_docs)] from development material only."""
    frame = load_frame("data/pools/pools.json", "data/pools/linkage_grid.json")
    pid, members = frame[0]
    assert pid == "pool_000", pid
    units = []
    for c in CELLS:
        _o, pu, _k, _t = build_units(os.path.join("results", "grid_A", c), 0, 7, 42,
                                     pools=[(pid, members)], o_docs=[])
        units.append((f"{c}/{pid}", pu[0][1], pu[0][2]))
    frags = [json.loads(l) for l in open("data/identifier/fragments.jsonl", encoding="utf-8") if l.strip()]
    by = defaultdict(list)
    for f in frags:
        if f["record_id"] < "r_0049":                   # r_0000..r_0048: never in the final sample
            by[f["record_id"]].append({"fragment_id": f["fragment_id"], "record_id": f["record_id"],
                                       "text": f["text"]})
    recs = sorted(by)
    assert len(recs) == 49 and recs[-1] == "r_0048"
    for i in range(7):
        ms = recs[i * 7:(i + 1) * 7]
        units.append((f"identifier-dev/{i}", [f for r in ms for f in by[r]], 7))
    return units


def run_attack(units, model, batch_size=EJ.BATCH_SIZE):
    out = {}
    for uid, frags, n in units:
        shown = [{"fragment_id": f["fragment_id"], "text": f["text"]} for f in frags]
        import random
        random.Random(_unit_seed(frags, 42, "order")).shuffle(shown)
        groups, _tel = EJ.attack(shown, n, model, seed=42, mask_seed=_unit_seed(frags, 42, "labels"),
                                 batch_size=batch_size)
        out[uid] = groups
    return out


def emit(path):
    """Child-process mode for check 6."""
    model = EJ.load_model()
    json.dump(run_attack(dev_units(), model), open(path, "w", encoding="utf-8"))


def git_blob(data):
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def main():
    if len(sys.argv) > 2 and sys.argv[1] == "--emit":
        emit(sys.argv[2])
        return
    rep = {"what": "score-blind development smoke test, embedding adversary (D14)", "checks": {}}
    ok = True

    # 0. pins
    path = EJ.model_path()
    bad = []
    for fn, (kind, want) in PINS.items():
        data = open(os.path.join(path, fn), "rb").read()
        got = hashlib.sha256(data).hexdigest() if kind == "sha256" else git_blob(data)
        bad += [fn] if got != want else []
    rep["checks"]["0_model_files_match_pins"] = {"ok": not bad, "mismatched": bad, "snapshot": path}
    ok &= not bad

    import sentence_transformers, torch, transformers
    rep["versions"] = {"sentence-transformers": sentence_transformers.__version__, "torch": torch.__version__,
                       "transformers": transformers.__version__, "numpy": np.__version__,
                       "torch_threads": torch.get_num_threads()}
    model = EJ.load_model()
    units = dev_units()
    texts = [f["text"] for _u, fr, _n in units for f in fr]
    rep["dev_material"] = {"units": len(units), "fragments": len(texts)}

    # 1 + 5. pipeline and validity
    t0 = time.perf_counter()
    recs = run_attack(units, model)
    t_attack = time.perf_counter() - t0
    invalid = []
    for uid, frags, n in units:
        g = recs[uid]
        placed = [x for grp in g for x in grp]
        if not (sorted(placed) == sorted(f["fragment_id"] for f in frags) and len(g) == n
                and all(len(grp) > 0 for grp in g)):
            invalid.append(uid)
    rep["checks"]["1_pipeline_runs"] = {"ok": True, "units": len(units)}
    rep["checks"]["5_valid_partition_exactly_N"] = {"ok": not invalid, "invalid_units": invalid}
    ok &= not invalid

    # 2. word-piece lengths
    tok = model.tokenizer
    lens = [len(tok(t, add_special_tokens=True)["input_ids"]) for t in texts]
    limit = model.max_seq_length
    rep["checks"]["2_wordpiece_lengths"] = {"ok": True, "limit": limit, "max": max(lens),
                                            "p99": float(np.percentile(lens, 99)),
                                            "over_limit": sum(l > limit for l in lens)}

    # 3. reproducibility
    a, b = EJ.embed(texts, model), EJ.embed(texts, model)
    rep["checks"]["3_embedding_reproducible"] = {"ok": bool(np.array_equal(a, b)),
                                                 "max_abs_diff": float(np.abs(a - b).max())}
    ok &= bool(np.array_equal(a, b))

    # 4. batch-size stability
    stab = {}
    for bs in (1, 16, 128):
        e = EJ.embed(texts, model, batch_size=bs)
        r = run_attack(units, model, batch_size=bs)
        stab[bs] = {"max_abs_diff_vs_64": float(np.abs(e - a).max()),
                    "same_reconstructions_as_64": r == recs}
    rep["checks"]["4_batch_size_stability"] = {"ok": all(v["same_reconstructions_as_64"] for v in stab.values()),
                                               "by_batch_size": stab}

    # 6. determinism across processes
    files = []
    for hs in ("0", "1"):
        p = os.path.join("results", "audit", f"_embedding_smoke_hs{hs}.json")
        subprocess.run([sys.executable, __file__, "--emit", p], env={**os.environ, "PYTHONHASHSEED": hs},
                       check=True)
        files.append(json.load(open(p, encoding="utf-8")))
        os.remove(p)
    same = files[0] == files[1] == json.loads(json.dumps(recs))
    rep["checks"]["6_deterministic_across_processes"] = {"ok": same}
    ok &= same

    # 7. grouper equivalence with memon_joint on TF-IDF similarity
    from memon_joint import group_known_n
    from memon_linkage import build_tfidf
    mism = 0
    for _uid, frags, n in units[:9]:
        ids = sorted(f["fragment_id"] for f in frags)
        tb = {f["fragment_id"]: f["text"] for f in frags}
        sim = build_tfidf(ids, tb)
        S = np.array([[sim(x, y) if x != y else 1.0 for y in ids] for x in ids])
        mism += EJ.cut_exact_n(ids, S, n, seed=42) != group_known_n(ids, tb, n, seed=42)[0]
    rep["checks"]["7_grouper_equals_memon_given_tfidf"] = {"ok": mism == 0, "mismatches": mism}
    ok &= mism == 0

    # 8. throughput
    EJ.embed(texts[:64], model)                                  # warm-up
    t0 = time.perf_counter()
    EJ.embed(texts, model)
    t_emb = time.perf_counter() - t0
    rate = len(texts) / t_emb
    per_frag_attack = t_attack / len(texts)
    rep["checks"]["8_throughput"] = {
        "ok": True, "embed_fragments_per_sec": rate, "attack_seconds_dev": t_attack,
        "attack_seconds_per_fragment": per_frag_attack,
        "projected_embedding_minutes_final": FINAL_FRAGMENTS / rate / 60,
        "projected_full_attack_minutes_final_single_process": FINAL_FRAGMENTS * per_frag_attack / 60,
        "note": "projection = measured dev rate x 62,527 final fragments; ordering cost grows faster than "
                "linearly with pool size, so the full-attack projection is a lower bound for the largest pools"}
    rep["PASS"] = bool(ok)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(rep, open(OUT + ".json", "w", encoding="utf-8"), indent=2)
    print(json.dumps(rep, indent=2))
    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
