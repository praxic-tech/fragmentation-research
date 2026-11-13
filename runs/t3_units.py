"""
t3_units.py — every evaluation unit tier 3 runs (RUN_DECISIONS D19, "tier 3
design": every condition tier 0 ran), and the exact texts the attacker sees for
each one, in the order its pair scores are stored.

One module, used by both sides, so the pair scores computed on the GPU and the
decoding run afterwards cannot disagree about a unit:
    runs/t3_score_eval.py   scores every unit's texts (GPU)
    runs/final_t3.py        decodes and scores the reconstructions (CPU)

Game J: the pools, shown order and masking seeds of runs/final_t0_attacker.py
        (build_units, shuffle by _unit_seed(.., "order"), mask seed
        _unit_seed(.., "labels")); texts in sorted masked-alias order, as
        crossenc_t3.masked_view produces them.
Game O: the presentation of runs/final_t0_extended.py
        (harness._masked_shuffled_order, seed 42); texts in sorted
        masked-label order, captured by running that same function.
No id, label or truth goes into a text list.
"""

import json
import os
import random
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for d in ("adversaries", "harness", "analysis"):
    sys.path.insert(0, os.path.join(ROOT, d))

import harness as H                                            # noqa: E402
import crossenc_t3 as T3                                       # noqa: E402
from joint_game import _unit_seed, build_units                 # noqa: E402

SEED = 42
J_GAMES = [("headlineJ", ["runs/final_headlineJ.json"]),
           ("gridJ", [f"runs/final_gridJ_w{k}.json" for k in (1, 2, 3, 4)]),
           ("identifierJ", ["runs/final_identifierJ.json"]),
           ("gradientJ", ["runs/gradient_J.json"]),
           ("singleTokenEdgeJ", ["runs/single_token_edge_J.json"])]
O_GAMES = [("headlineO", ["runs/final_headlineO.json"]),
           ("gridO", [f"runs/final_gridO_w{k}.json" for k in (1, 2, 3)])]
N_J, N_O = 46 + 9 * 24 + 20 + 3 * 20 + 2 * 20, 100 + 9 * 30      # D19 tier 3 evaluation scope


def cell_name(cell):
    return os.path.basename(os.path.normpath(cell))


def _rel(path):
    return os.path.join(ROOT, path)


def j_units():
    """(game, cell, pool id, members) for every Game J unit, in a fixed order."""
    for game, paths in J_GAMES:
        for path in paths:
            b = json.load(open(_rel(path), encoding="utf-8"))["build"]
            for cell in b["cells"]:
                for pid, members in b["pools"]:
                    yield game, cell, pid, members


def j_prepare(cell, pid, members):
    """Exactly runs/final_t0_attacker.run_pool's preamble."""
    _o, units, key, truth = build_units(_rel(cell), 0, len(members), SEED, pools=[(pid, members)], o_docs=[])
    (_pid, frags, n_docs), = units
    shown = [{"fragment_id": f["fragment_id"], "text": f["text"]} for f in frags]
    random.Random(_unit_seed(frags, SEED, "order")).shuffle(shown)
    ms = _unit_seed(frags, SEED, "labels")
    return frags, key, truth, shown, n_docs, ms


def j_texts(shown, ms):
    return T3.masked_view(shown, SEED, ms)[1]


def o_units():
    """(game, cell, doc id, fragments, key) for every Game O unit, in a fixed order."""
    for game, paths in O_GAMES:
        for path in paths:
            b = json.load(open(_rel(path), encoding="utf-8"))["build"]
            for cell in b["cells"]:
                o, _p, key, _t = build_units(_rel(cell), 0, 7, SEED, pools=[], o_docs=b["o_docs"])
                for rid, frags, _n in o:
                    yield game, cell, rid, frags, key


def o_texts(frags):
    """The texts an orderer sees under harness._masked_shuffled_order, in sorted-label order."""
    ids = [f["fragment_id"] for f in frags]
    text = {f["fragment_id"]: f["text"] for f in frags}
    seen = []

    def capture(shown, ltext):
        seen.append([ltext[lab] for lab in sorted(shown)])
        return list(shown)
    capture.__name__ = "t3_capture"
    H._masked_shuffled_order(capture, ids, text, H.DEFAULT_SEED)
    return seen[0]


def all_unit_texts():
    """[(kind, game, cell name, unit id, texts)] for the whole evaluation, J then O."""
    out = []
    for game, cell, pid, members in j_units():
        _f, _k, _t, shown, _n, ms = j_prepare(cell, pid, members)
        out.append(("J", game, cell_name(cell), pid, j_texts(shown, ms)))
    for game, cell, rid, frags, _key in o_units():
        out.append(("O", game, cell_name(cell), rid, o_texts(frags)))
    nj = sum(1 for u in out if u[0] == "J")
    assert (nj, len(out) - nj) == (N_J, N_O), f"expected {N_J} J and {N_O} O units, got {nj} and {len(out) - nj}"
    return out


if __name__ == "__main__":
    from collections import Counter
    us = all_unit_texts()
    by = Counter()
    pairs = Counter()
    words = Counter()
    for kind, game, cell, _uid, texts in us:
        m, u = len(texts), len(set(texts))
        by[(game, cell)] += 1
        pairs[(game, cell)] += u * (u - 1) + sum(1 for c in Counter(texts).values() if c > 1)
        wl = [len(t.split()) for t in texts]
        words[(game, cell)] += (u - 1) * 2 * sum(min(w, 60) for w in wl)   # rough: each text in 2(u-1) pairs
    for k in sorted(by):
        print(f"{k[0]:<18}{k[1]:<34}{by[k]:>5} units {pairs[k]:>11,} pairs  ~{words[k] / max(pairs[k], 1):5.1f} words/pair")
    print(f"total {len(us)} units, {sum(pairs.values()):,} pairs")
