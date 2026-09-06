"""
joint_game.py — the three attack conditions on one corpus, scored comparably.

    game O (oracle)  one document's fragments, shuffled -> recover the ORDER.
                     Membership is given for free. An upper bound on the
                     adversary, not a threat model: it assumes linkage already
                     solved.
    game L           one pool's fragments from N documents, mixed -> recover
                     which fragments share a document. No ordering asked.
    game J (joint)   the same pool -> recover membership AND order together.
                     This is the condition the threat model actually describes:
                     an adversary holding a fragmented database has everything
                     mixed and is given nothing.

WHY RUN ALL THREE
-----------------
J is the realistic number. O is the ceiling. The GAP between them is the result
worth reporting: it says how much of the defence is linkage and how much is
ordering. L falls out of J for free (drop the ordering) and is kept as a
separate arm here only to check that asking for order does not degrade the
grouping — if J's linkage is materially worse than L's, the joint task is
costing the model something and that has to be disclosed.

Information flows one way: L is derivable from J, J is not derivable from O or
L. That asymmetry is why data should be collected jointly even if the paper
ends up reporting the decomposition.

EVERY RESPONSE IS STORED RE-SCORABLE
------------------------------------
Each row keeps the alias map, the presentation order actually shown, the raw
response before parsing, and the prompt hash. Without the alias map a masked
response is unmappable back to fragment ids and the money is wasted; the map
being reproducible "because it is seeded" is not good enough, since reproducing
it means replaying a loop whose RNG advances across iterations. With these
fields any future metric — or a revised threat model — is recomputed from disk
instead of re-purchased.

    python adversaries/joint_game.py --docs 25 --provider groq \
        --model openai/gpt-oss-120b --pool-size 3 --games O L J
    python adversaries/joint_game.py --score-only
"""

import argparse
import hashlib
import json
import os
import random
import sys
import time
from datetime import datetime, timezone

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(BASE_DIR)
for _p in (os.path.join(ROOT, "harness"), os.path.join(ROOT, "datagen"), BASE_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from masking import mask_fragment_ids, preflight, preflight_summary   # noqa: E402
from scoring import score_ordering, score_linkage, trivial_floor, check_partition  # noqa: E402
from llm_adversary import PROVIDERS, call_model, make_client, load_jsonl  # noqa: E402

import numpy as np                                                    # noqa: E402

DEFAULT_CELL = os.path.join(ROOT, "results", "grid", "pilot_reference")
DEFAULT_OUT = os.path.join(ROOT, "results", "joint_pilot")
SEED = 42


# ── prompts ──────────────────────────────────────────────────────────────────

def prompt_O(items):
    lines = "\n".join(f"{a}: {t}" for a, t in items)
    return ("These fragments are pieces of ONE record, shuffled. "
            "Put them back in their most likely original order.\n\n"
            "Fragments:\n" + lines +
            "\n\nReturn ONLY a JSON array of the item labels in your best order.")


def prompt_L(items, n_records):
    lines = "\n".join(f"{a}: {t}" for a, t in items)
    return (f"Below are {len(items)} shuffled fragments from {n_records} different "
            "records. Group them back into the records they came from. Different "
            "records may contain different numbers of fragments. Use every item "
            "exactly once.\n\n"
            "Fragments:\n" + lines +
            f"\n\nReturn ONLY a JSON array of {n_records} arrays, each an array of "
            "the item labels that belong to one record. No explanation, no markdown.")


def prompt_J(items, n_records):
    """Joint: membership and order in one answer.

    Deliberately the same input as L so the two are comparable — the only
    difference is what the answer must contain.
    """
    lines = "\n".join(f"{a}: {t}" for a, t in items)
    return (f"Below are {len(items)} shuffled fragments taken from {n_records} "
            "different records and mixed together. You are given no information "
            "about which fragment came from which record.\n\n"
            "Do two things at once:\n"
            f"  1. Work out which fragments belong to the same record ({n_records} "
            "records in total; they may contain different numbers of fragments).\n"
            "  2. Within each record, put its fragments back into their original "
            "order.\n\n"
            "Use every item exactly once.\n\n"
            "Fragments:\n" + lines +
            f"\n\nReturn ONLY a JSON array of {n_records} arrays. Each inner array "
            "holds the item labels of one record, IN THEIR RECONSTRUCTED ORDER. "
            "No explanation, no markdown.")


# ── presentation ─────────────────────────────────────────────────────────────

def present(fragments, seed):
    """Mask ids, shuffle, and return (items, alias_map, shown_order).

    alias_map is returned and stored, never recomputed. shown_order records what
    the model actually saw so a positional-leak check is possible after the fact.
    """
    masked, id_map = mask_fragment_ids(fragments, seed=seed)
    shown = list(masked)
    random.Random(seed).shuffle(shown)
    items = [(m["fragment_id"], m["text"]) for m in shown]
    return items, id_map, [m["fragment_id"] for m in shown]


def sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


# ── running ──────────────────────────────────────────────────────────────────

def size_reservation(prompt, n_items, tpm_limit=None):
    """Output reservation, sized to the answer AND to the rate limit.

    Two facts collide here. A compliant joint answer costs ~3.0 output tokens
    per fragment -- MEASURED, it is just a list of masked labels. And providers
    count the RESERVATION, not the usage, against tokens-per-minute. So an
    over-generous cap gets a request rejected for a budget it would never have
    spent: reserving 45/fragment is what made pools of 7 look impossible on an
    8k tier when they fit comfortably.

    Ask for 12/fragment (4x the measured need). If that would not fit under
    tpm_limit alongside the prompt, shrink to what fits and say so, rather than
    sending a request guaranteed to 429.
    """
    want = max(512, min(16000, n_items * 12 + 300))
    if not tpm_limit:
        return want
    room = tpm_limit - (len(prompt) // 4) - 200          # 200 = headroom
    if room < want:
        floor_need = n_items * 3
        if room < floor_need:
            print(f"  [warn] {n_items} fragments need >={floor_need} output tokens "
                  f"but only {room} fit under the {tpm_limit} limit — expect truncation")
        return max(256, room)
    return want


def done_units(path):
    if not os.path.exists(path):
        return set()
    return {r["unit"] for r in load_jsonl(path)}


def append(path, row):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(row) + "\n")
        fh.flush()


def run_game(client, game, units, model, out_path, seed, pause=2.0,
             tpm_limit=None):
    """units: list of (unit_id, fragments, n_records). Appends one row each."""
    already = done_units(out_path)
    ok, failed = 0, []
    for unit_id, frags, n_records in units:
        if unit_id in already:
            continue
        items, id_map, shown = present(frags, seed)
        if game == "O":
            prompt = prompt_O(items)
        elif game == "L":
            prompt = prompt_L(items, n_records)
        else:
            prompt = prompt_J(items, n_records)

        preflight(prompt, where=f"{game}/{unit_id}")
        # Size the reservation to the answer: providers count max_tokens against
        # tokens-per-minute, and a flat cap fails rate limits the call is
        # nowhere near using.
        # MEASURED: a compliant joint answer costs ~3.0 output tokens per
        # fragment (a list of masked labels, nothing else). 12/fragment is a 4x
        # safety margin. This is not cosmetic -- providers count the RESERVATION
        # against tokens-per-minute, so an over-generous cap fails rate limits
        # the call is nowhere near using. Reserving 45/fragment is what made
        # pools of 7 look impossible on an 8k TPM tier when they fit easily.
        max_tok = size_reservation(prompt, len(items), tpm_limit)
        try:
            raw = call_model(client, prompt, model, temperature=None,
                             max_tokens=max_tok)
        except Exception as err:
            failed.append(unit_id)
            print(f"  [skip] {game}/{unit_id} ({len(items)} frags): {str(err)[:100]}")
            time.sleep(pause)
            continue

        append(out_path, {
            "game": game, "unit": unit_id, "model": model, "seed": seed,
            "n_fragments": len(items), "n_records": n_records,
            "alias_map": id_map,               # label -> fragment_id, NEVER recomputed
            "shown_order": shown,              # what the model actually saw
            "prompt_sha": sha(prompt),
            "prompt": prompt,
            "raw_response": raw,               # parsed structure, pre-scoring
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        })
        ok += 1
        print(f"  {game}/{unit_id}: {len(items)} frags -> answered")
        time.sleep(pause)
    print(f"  game {game}: {ok} new, {len(already)} cached, {len(failed)} failed"
          + (f" ({', '.join(failed)})" if failed else ""))
    return failed


# ── scoring ──────────────────────────────────────────────────────────────────

def _as_groups(raw):
    """Normalise a response into a list of lists of labels."""
    if isinstance(raw, list) and raw and isinstance(raw[0], list):
        return [[str(x) for x in g] for g in raw]
    if isinstance(raw, list):
        return [[str(x) for x in raw]]
    return []


def _align(guessed, true_groups):
    """Greedy max-overlap match of guessed groups to true records.

    Ordering only means something inside a group that corresponds to a record.
    Matching by overlap (rather than assuming position) is what makes tau
    computable at all when membership is imperfect.
    """
    pairs = []
    used_g, used_t = set(), set()
    cand = []
    for gi, g in enumerate(guessed):
        gs = set(g)
        for rid, ids in true_groups.items():
            ov = len(gs & set(ids))
            if ov:
                cand.append((ov, gi, rid))
    for ov, gi, rid in sorted(cand, key=lambda x: -x[0]):
        if gi in used_g or rid in used_t:
            continue
        used_g.add(gi); used_t.add(rid)
        pairs.append((gi, rid, ov))
    return pairs


def score_row(row, true_order, true_groups_by_unit):
    game = row["game"]
    id_map = row["alias_map"]
    groups = _as_groups(row["raw_response"])
    # translate labels -> fragment ids, dropping anything invented
    groups = [[id_map[l] for l in g if l in id_map] for g in groups]
    groups = [g for g in groups if g]

    if game == "O":
        rid = row["unit"]
        guess = groups[0] if groups else []
        truth = true_order[rid]
        if len(guess) != len(truth) or set(guess) != set(truth):
            return {"game": "O", "unit": rid, "malformed": True}
        return {"game": "O", "unit": rid, "malformed": False,
                "tau": score_ordering(guess, truth)["tau"], "n": len(truth)}

    tg = true_groups_by_unit[row["unit"]]
    all_ids = {i for v in tg.values() for i in v}

    # The model DROPS fragments despite being told to use every item exactly
    # once -- measured 1-4 per pool typically, 44 of 75 in the worst case. A
    # dropped fragment that simply vanishes from the guess inflates precision
    # (you are only scored on pairs you claimed) while deflating recall: bug 8's
    # signature. Placing each unplaced fragment in its own singleton group is
    # the faithful reading -- an attacker who could not place it claims no pairs
    # for it -- and it makes the answer a valid partition so the coverage line
    # means something. n_dropped is reported so the repair is never invisible.
    placed = {f for g in groups for f in g}
    dropped = sorted(all_ids - placed)
    groups = groups + [[f] for f in dropped]
    gdict = {str(i): g for i, g in enumerate(groups)}
    cov = check_partition(gdict, all_ids)
    lk = score_linkage(gdict, tg, all_fragment_ids=all_ids)
    fl = trivial_floor(tg)
    out = {"game": game, "unit": row["unit"], "malformed": False,
           "n_dropped": len(dropped),
           "coverage_frac": len(placed & all_ids) / len(all_ids) if all_ids else 0.0,
           "n_groups_guessed": len(groups) - len(dropped), "n_groups_true": len(tg),
           "f1": lk["f1"], "floor": fl["f1"], "margin": lk["f1"] - fl["f1"],
           "partition_valid": cov["valid"], "coverage": cov}

    if game == "J":
        taus, exact, matched = [], 0, 0
        for gi, rid, ov in _align(groups, tg):
            truth = true_order[rid]
            guess = [f for f in groups[gi] if f in set(truth)]
            matched += 1
            if len(guess) >= 2:
                sub = [f for f in truth if f in set(guess)]
                if len(set(guess)) == len(guess) and set(guess) == set(sub):
                    t = score_ordering(guess, sub)["tau"]
                    if not np.isnan(t):
                        taus.append(t)
            if set(groups[gi]) == set(truth) and groups[gi] == truth:
                exact += 1
        jp = score_joint(groups, true_order, list(tg))
        jf = joint_floor(true_order, list(tg))
        out.update({"tau_in_matched": float(np.mean(taus)) if taus else float("nan"),
                    "n_matched_groups": matched,
                    "exact_records": exact,
                    "exact_rate": exact / len(tg) if tg else 0.0,
                    # headline joint metric: ordered-pair F1 against the
                    # one-bucket-arbitrary-order floor
                    "joint_f1": jp["f1"], "joint_p": jp["precision"],
                    "joint_r": jp["recall"], "joint_floor": jf["f1"],
                    "joint_margin": jp["f1"] - jf["f1"]})
    return out


# ── driver ───────────────────────────────────────────────────────────────────

def build_units(cell_dir, n_docs, pool_size, seed):
    """Return (per-document units for O, per-pool units for L/J, truth tables)."""
    frags = load_jsonl(os.path.join(cell_dir, "prose_fragments.jsonl"))
    key = {r["record_id"]: r["order"]
           for r in load_jsonl(os.path.join(cell_dir, "prose_answer_key.jsonl"))}
    by_rec = {}
    for f in frags:
        by_rec.setdefault(f["record_id"], []).append(f)

    rids = sorted(by_rec)[:n_docs]
    o_units = [(r, by_rec[r], 1) for r in rids]

    pools, pool_truth = [], {}
    for i in range(0, len(rids), pool_size):
        members = rids[i:i + pool_size]
        if len(members) < 2:            # a pool of one has no linkage question
            break
        pid = f"pool_{i // pool_size:02d}"
        pool_frags = [f for r in members for f in by_rec[r]]
        pools.append((pid, pool_frags, len(members)))
        pool_truth[pid] = {r: [f["fragment_id"] for f in by_rec[r]] for r in members}
    return o_units, pools, key, pool_truth


def report(out_dir, key, pool_truth):
    rows = []
    for g in ("O", "L", "J"):
        p = os.path.join(out_dir, f"{g}.jsonl")
        if os.path.exists(p):
            rows += [score_row(r, key, pool_truth) for r in load_jsonl(p)]

    O = [r for r in rows if r["game"] == "O" and not r.get("malformed")]
    Om = [r for r in rows if r["game"] == "O" and r.get("malformed")]
    L = [r for r in rows if r["game"] == "L"]
    J = [r for r in rows if r["game"] == "J"]

    print("\n" + "=" * 74)
    print(" THREE ATTACK CONDITIONS, SAME CORPUS, SAME MODEL")
    print("=" * 74)
    if O:
        t = [r["tau"] for r in O]
        print(f"\nGAME O  (oracle linkage: membership given, order only)")
        print(f"  scored {len(O)}/{len(O)+len(Om)} documents   malformed {len(Om)}")
        print(f"  tau  mean {np.mean(t):+.4f}   median {np.median(t):+.4f}   "
              f"min {min(t):+.3f}  max {max(t):+.3f}")

    for name, S in (("GAME L  (grouping only, no ordering asked)", L),
                    ("GAME J  (joint: membership AND order, nothing given)", J)):
        if not S:
            continue
        print(f"\n{name}")
        print(f"  pools scored {len(S)}")
        print(f"  linkage F1   mean {np.mean([r['f1'] for r in S]):.4f}   "
              f"floor {np.mean([r['floor'] for r in S]):.4f}   "
              f"margin {np.mean([r['margin'] for r in S]):+.4f}")
        print(f"  groups       guessed {np.mean([r['n_groups_guessed'] for r in S]):.1f} "
              f"vs {np.mean([r['n_groups_true'] for r in S]):.1f} asked   "
              f"exact count {sum(1 for r in S if r['n_groups_guessed']==r['n_groups_true'])}/{len(S)}")
        print(f"  partition    valid {sum(1 for r in S if r['partition_valid'])}/{len(S)}"
              f"   (after repairing dropped fragments to singletons)")
        print(f"  COVERAGE     model placed {np.mean([r['coverage_frac'] for r in S]):.1%} "
              f"of fragments   dropped {sum(r['n_dropped'] for r in S)} total, "
              f"worst pool {max(r['n_dropped'] for r in S)}")
        if name.startswith("GAME J"):
            print(f"  JOINT ordered-pair F1   mean {np.mean([r['joint_f1'] for r in S]):.4f}"
                  f"   floor {np.mean([r['joint_floor'] for r in S]):.4f}"
                  f"   margin {np.mean([r['joint_margin'] for r in S]):+.4f}")
            tj = [r["tau_in_matched"] for r in S if not np.isnan(r["tau_in_matched"])]
            print(f"  tau in matched groups   mean {np.mean(tj):+.4f}  (n={len(tj)} pools)")
            print(f"  records recovered EXACTLY (membership and order): "
                  f"{sum(r['exact_records'] for r in S)}/{sum(r['n_groups_true'] for r in S)}"
                  f"  ({np.mean([r['exact_rate'] for r in S]):.1%})")

    if O and J:
        tj = [r["tau_in_matched"] for r in J if not np.isnan(r["tau_in_matched"])]
        if tj:
            print(f"\nTHE GAP  oracle tau {np.mean([r['tau'] for r in O]):+.4f}  ->  "
                  f"joint tau {np.mean(tj):+.4f}   "
                  f"({np.mean([r['tau'] for r in O]) - np.mean(tj):+.4f})")
    if L and J:
        print(f"COST OF ASKING FOR ORDER  linkage margin "
              f"{np.mean([r['margin'] for r in L]):+.4f} (L) -> "
              f"{np.mean([r['margin'] for r in J]):+.4f} (J)")
    return rows


def parse_args():
    ap = argparse.ArgumentParser(description="Run games O, L and J on one corpus.")
    ap.add_argument("--cell", default=DEFAULT_CELL)
    ap.add_argument("--out-dir", default=DEFAULT_OUT)
    ap.add_argument("--docs", type=int, default=25)
    ap.add_argument("--pool-size", type=int, default=3)
    ap.add_argument("--provider", default="groq", choices=list(PROVIDERS))
    ap.add_argument("--model", default=None)
    ap.add_argument("--games", nargs="+", default=["O", "L", "J"])
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--pause", type=float, default=2.0)
    ap.add_argument("--tpm-limit", type=int, default=8000,
                    help="provider tokens-per-minute ceiling; the output "
                         "reservation is shrunk to fit under it")
    ap.add_argument("--score-only", action="store_true")
    return ap.parse_args()


def main():
    a = parse_args()
    model = a.model or PROVIDERS[a.provider][1]
    o_units, pools, key, pool_truth = build_units(a.cell, a.docs, a.pool_size, a.seed)
    print(f"corpus : {len(o_units)} documents, {len(pools)} pools of up to {a.pool_size}")
    print(f"model  : {model} via {a.provider}")

    if not a.score_only:
        client = make_client(a.provider)
        for g in a.games:
            units = o_units if g == "O" else pools
            print(f"\n[game {g}] {len(units)} units")
            run_game(client, g, units, model,
                     os.path.join(a.out_dir, f"{g}.jsonl"), a.seed,
                     pause=a.pause, tpm_limit=a.tpm_limit)
        print("\n" + preflight_summary())

    report(a.out_dir, key, pool_truth)




# ── the joint metric ─────────────────────────────────────────────────────────

def _ordered_pairs(groups):
    """Every (earlier, later) pair implied by a list of ORDERED groups."""
    out = set()
    for g in groups:
        for i, a in enumerate(g):
            for b in g[i + 1:]:
                out.add((a, b))
    return out


def score_joint(guessed_groups, true_order, members):
    """Ordered-pair precision / recall / F1 for a joint answer.

    Generalises the two metrics already in use rather than inventing a third
    scale. An unordered co-membership pair is what score_linkage counts; this
    counts the same pair WITH its direction, so:

        ignore direction              -> exactly score_linkage's F1
        fix membership to perfect     -> concordant-pair counting, i.e. tau

    A pair split across groups is a miss. A pair grouped together but ordered
    backwards is both a false positive (asserted something untrue) and a false
    negative (failed to assert the truth), which is the right charge for it.

    Edge case worth disclosing: a perfectly grouped but fully REVERSED document
    scores 0 here, because every pair points the wrong way. That agrees with
    tau = -1 on the same output, but "reversed" is arguably a full
    reconstruction in information terms, so it belongs in methods.
    """
    guessed = _ordered_pairs(guessed_groups)
    truth = _ordered_pairs([true_order[r] for r in members])
    tp = len(guessed & truth)
    p = tp / len(guessed) if guessed else 0.0
    r = tp / len(truth) if truth else 0.0
    return {"precision": p, "recall": r,
            "f1": 2 * p * r / (p + r) if (p + r) else 0.0,
            "tp": tp, "n_guessed": len(guessed), "n_true": len(truth)}


def joint_floor(true_order, members, seed=0, trials=200):
    """Floor: every fragment in ONE bucket, in an arbitrary order.

    The joint counterpart of scoring.trivial_floor. Recall is ~0.5 rather than
    1.0 because a single arbitrary sequence gets about half its directions right
    by chance -- which is exactly why a joint F1 must be read against this and
    not against the linkage floor.
    """
    ids = [f for r in members for f in true_order[r]]
    rng = random.Random(seed)
    acc = {"precision": 0.0, "recall": 0.0, "f1": 0.0}
    for _ in range(trials):
        shuffled = list(ids)
        rng.shuffle(shuffled)
        s = score_joint([shuffled], true_order, members)
        for k in acc:
            acc[k] += s[k]
    # An EXPECTATION over shuffles, not one draw. A single shuffle is a sample
    # with real variance -- on a small pool it can land on 0 by luck, and a
    # floor that moves between calls is worse than no floor.
    return {k: v / trials for k, v in acc.items()}


if __name__ == "__main__":
    main()
