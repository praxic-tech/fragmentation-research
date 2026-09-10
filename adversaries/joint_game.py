"""
joint_game.py — the three attack conditions on one corpus, scored comparably.

    game O           one document's fragments, shuffled -> recover the ORDER.
                     Membership is given for free. A MEMBERSHIP-ORACLE
                     REFERENCE, not a ceiling: for a prompted model, changing
                     the task can hurt as easily as help, so J is not bounded
                     by it.
    game L           one pool's fragments from N documents, mixed -> recover
                     which fragments share a document. No ordering asked.
    game J (joint)   the same pool -> recover membership AND order together.
                     This is the condition the threat model actually describes:
                     an adversary holding a fragmented database has everything
                     mixed and is given nothing.

WHY RUN ALL THREE
-----------------
J is the realistic number. O is a membership-oracle reference. The GAP between
them is NOT a clean measure of "how much of the defence is linkage" -- the two
are differently prompted and on different scales, so the gap carries task
coupling as well. The F1_J = F1_L * q decomposition is the clean evidence for
where J fails. L falls out of J for free (drop the ordering) and is kept as a
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
from joint_metrics import reconstruction_detail                       # noqa: E402
from repair import NoModelAnswer, run_with_repair                     # noqa: E402
from scoring import score_ordering, score_linkage, trivial_baseline, check_partition  # noqa: E402
from joint_metrics import (analytic_baseline, advantage, decompose,      # noqa: E402
                          micro_q, ordered_pairs, score_joint)
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


# A unit whose answer is mostly OUR completion policy measures the policy, not
# the attacker. Past this share the cell is refused as a defence result; see
# cell_integrity(). A judgement call, stated here so it can be argued with.
POLICY_CAP = 0.25
# llm_adversary.call_model's message once its own 429 backoff gives up.
QUOTA_MARKER = "Too many transient failures"


def log_failure(out_path, game, unit_id, n_items, reason):
    """Every unit the model never answered, durably, for the audit trail."""
    append(out_path.replace(".jsonl", ".failures.jsonl"), {
        "game": game, "unit": unit_id, "n_fragments": n_items,
        "reason": reason, "at": datetime.now(timezone.utc).isoformat()})


def run_game(client, game, units, model, out_path, seed, pause=2.0,
             tpm_limit=None, max_retries=1):
    """units: list of (unit_id, fragments, n_records). Appends one row each."""
    already = done_units(out_path)
    ok, failed = 0, []
    quota_hit = False
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

        # REPAIR. harness/repair.py was built in Phase 1 for exactly this and
        # was never wired in here, which cost more than it looks:
        #
        #   game O   a malformed answer is DROPPED from the sample, so tau is
        #            computed on survivors. On the free-tier probe 12 of 32
        #            units dropped, and the drop rate tracked fragment count
        #            (6/8 at 44.5 frags/doc vs 1/8 at 26.4) -- so the bias was
        #            largest exactly where the task was hardest.
        #   game J   an incomplete answer is still scored and omission costs
        #            recall, so the number is DEPRESSED rather than inflated.
        #            Across the whole J pilot, 0 of 14 units ever returned a
        #            complete valid partition.
        #
        # The feedback is bookkeeping only -- which labels are missing,
        # duplicated or invented -- never a hint about grouping or order.
        expected = set(id_map)
        state = {"raw": None, "err": None}

        def attempt(feedback, _p=prompt, _mt=max_tok, _u=unit_id, _g=game):
            text = _p if not feedback else f"{_p}\n\n{feedback}"
            preflight(text, where=f"{_g}/{_u} repair" if feedback
                      else f"{_g}/{_u}")
            raw = call_model(client, text, model, temperature=None,
                             max_tokens=_mt)
            state["raw"] = raw
            return _as_groups(raw)

        try:
            groups, rec = run_with_repair(attempt, expected,
                                          max_retries=max_retries)
        except NoModelAnswer as err:
            # The model never answered: quota, rate limit, transport. That is
            # not an attack outcome and is never scored. Not written, so a
            # re-run of the same command asks exactly this unit again.
            failed.append(unit_id)
            log_failure(out_path, game, unit_id, len(items), str(err))
            print(f"  [NO ANSWER] {game}/{unit_id} ({len(items)} frags): "
                  f"not written, will be retried -- {str(err)[:90]}")
            if QUOTA_MARKER in str(err):
                # Grinding on only walks every remaining unit into the same
                # wall -- on the free-tier grid that ended in a wall-clock
                # timeout killing the process mid-cell. Stop; resume later.
                quota_hit = True
                print("  [QUOTA] provider limit reached -- ending this pass; "
                      "the run cools down and retries what is unanswered.")
                break
            time.sleep(pause)
            continue

        # Game O wants ONE order over every fragment, not a partition. Flatten
        # in order of appearance: what the model said first, then whatever it
        # forgot, appended deterministically. That is the exhaustion policy for
        # an ordering task -- arbitrary for the forgotten tail, and recorded as
        # such in `repair` rather than hidden behind a dropped unit.
        raw = [x for g in groups for x in g] if game == "O" else groups

        append(out_path, {
            "game": game, "unit": unit_id, "model": model, "seed": seed,
            "n_fragments": len(items), "n_records": n_records,
            "alias_map": id_map,               # label -> fragment_id, NEVER recomputed
            "shown_order": shown,              # what the model actually saw
            "prompt_sha": sha(prompt),
            "prompt": prompt,
            "raw_response": raw,               # parsed structure, pre-scoring
            "repair": rec,                     # calls, retries, forced completion
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        })
        ok += 1
        tag = "answered"
        if rec["repair_attempted"]:
            tag = ("answered after repair" if rec["final_attempt_valid"]
                   else f"completed by policy (+{rec['singletons_added']})")
        if rec.get("policy_share", 0.0) > POLICY_CAP:
            tag += (f"   [WARN model placed only "
                    f"{1 - rec['policy_share']:.0%} of fragments]")
        print(f"  {game}/{unit_id}: {len(items)} frags -> {tag}")
        time.sleep(pause)
    print(f"  game {game}: {ok} new, {len(already)} cached, {len(failed)} failed"
          + (f" ({', '.join(failed)})" if failed else ""))
    return failed, quota_hit


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


def _policy_share(row):
    """Fraction of this unit's fragments placed by OUR completion policy."""
    rec = row.get("repair") or {}
    if "policy_share" in rec:
        return rec["policy_share"]
    n = row.get("n_fragments") or 0
    return (rec.get("singletons_added", 0) / n) if n else 0.0


def _no_model_answer(row):
    """True for rows the pre-fix code wrote after EVERY attempt errored.

    Those orders are 100% completion policy. They exist in older result files,
    so this reads the stored attempt log rather than trusting that no such row
    can exist any more.
    """
    att = (row.get("repair") or {}).get("attempts") or []
    return bool(att) and all(a.get("error") for a in att)


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
        # tau alone is generous: it scores broad direction over every pair and
        # can look healthy while nothing sits in the right place. Report what an
        # attacker actually gets back -- exact positions, displacement, and the
        # longest intact stretch -- beside it. All free from the answer key.
        detail = reconstruction_detail(guess, truth) or {}
        return {"game": "O", "unit": rid, "malformed": False,
                "tau": score_ordering(guess, truth)["tau"], "n": len(truth),
                "policy_share": _policy_share(row),
                **{k: detail[k] for k in
                   ("exact_positions", "exact_fraction", "mean_shift",
                    "longest_run", "run_fraction") if k in detail}}

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
    bl = trivial_baseline(tg)
    out = {"game": game, "unit": row["unit"], "malformed": False,
           "n_dropped": len(dropped),
           "coverage_frac": len(placed & all_ids) / len(all_ids) if all_ids else 0.0,
           "n_groups_guessed": len(groups) - len(dropped), "n_groups_true": len(tg),
           "f1": lk["f1"], "baseline": bl["f1"],
           "advantage": advantage(lk["f1"], bl["f1"]),
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
        dec = decompose(groups, true_order, list(tg))
        out.update({"tau_in_matched": float(np.mean(taus)) if taus else float("nan"),
                    "n_matched_groups": matched,
                    "exact_records": exact,
                    "exact_rate": exact / len(tg) if tg else 0.0,
                    # headline: ordered-pair F1 against the ANALYTIC
                    # one-bucket-arbitrary-order baseline, plus the
                    # F1_J = F1_L * q decomposition. q is None when K == 0.
                    "joint_f1": jp["f1"], "joint_p": jp["precision"],
                    "joint_r": jp["recall"],
                    "joint_baseline": dec["baseline_joint"],
                    "joint_advantage": dec["a_joint"],
                    "j_linkage_f1": dec["f1_linkage"],
                    "C": dec["C"], "K": dec["K"], "q": dec["q"],
                    "a_order": dec["a_order"]})
    return out


# ── driver ───────────────────────────────────────────────────────────────────

def build_units(cell_dir, n_docs, pool_size, seed, pools=None, o_docs=None):
    """Return (per-document units for O, per-pool units for L/J, truth tables).

    Without `pools`, pools are consecutive runs of the first n_docs sorted ids:
    a free-tier convenience, NOT a sampling frame. The paid run passes the
    PRE-REGISTERED pools explicitly as [(pool_id, [record_id, ...])].

    Every pre-registered member must exist in the cell, or this raises. It does
    not drop missing members: the grid cells were cut from the length-stratified
    ordering sample, and 107 of the 175 members of the pre-registered grid pools
    are not in it. Dropping them would quietly turn random 7-document pools into
    smaller, non-random ones, and every score would still look reasonable.
    """
    frags = load_jsonl(os.path.join(cell_dir, "prose_fragments.jsonl"))
    key = {r["record_id"]: r["order"]
           for r in load_jsonl(os.path.join(cell_dir, "prose_answer_key.jsonl"))}
    by_rec = {}
    for f in frags:
        by_rec.setdefault(f["record_id"], []).append(f)

    if pools is not None:
        wanted = {r for _pid, members in pools for r in members}
        wanted |= set(o_docs or [])
        missing = sorted(wanted - set(by_rec))
        if missing:
            raise ValueError(
                f"{len(missing)} of {len(wanted)} pre-registered documents are "
                f"not in {cell_dir}, e.g. {missing[:3]}. This cell was cut from "
                "a different document sample. Re-cut it on the frame's "
                "documents; never drop members to make the pools fit.")
        pool_units = [(pid, [f for r in members for f in by_rec[r]], len(members))
                      for pid, members in pools]
        pool_truth = {pid: {r: [f["fragment_id"] for f in by_rec[r]]
                            for r in members} for pid, members in pools}
        rids = list(o_docs) if o_docs is not None else []
        return ([(r, by_rec[r], 1) for r in rids], pool_units, key, pool_truth)

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


def cell_integrity(scored, expected_units, cap=POLICY_CAP):
    """May this set of scored units be reported as a defence result at all?

    Two failures, both of which printed clean-looking, wrong means on the
    free-tier grid before this existed:

      incomplete     an expected unit has no model answer -- never written, or
                     written by the old code with every attempt errored and
                     the whole order supplied by the completion policy
      policy-heavy   the model answered but placed under (1 - cap) of the
                     fragments; the rest of the order is ours, so the score
                     measures model capacity plus our policy, not the cut
    """
    by_unit = {r["unit"]: r for r in scored}
    missing = sorted(u for u in expected_units
                     if u not in by_unit or by_unit[u].get("no_model_answer"))
    heavy = sorted(u for u, r in by_unit.items()
                   if not r.get("no_model_answer")
                   and r.get("policy_share", 0.0) > cap)
    shares = [r.get("policy_share", 0.0) for r in scored
              if not r.get("no_model_answer")]
    return {"ok": not missing and not heavy,
            "expected": len(expected_units),
            "answered": len(expected_units) - len(missing),
            "missing": missing, "policy_heavy": heavy,
            "policy_share": (sum(shares) / len(shares)) if shares else 0.0}


def integrity_gate(out_dir, key, pool_truth, expected):
    """Per game: may a mean be printed? Returns the set of refused games."""
    refused = set()
    print()
    print("INTEGRITY")
    for gname, exp in expected.items():
        p = os.path.join(out_dir, f"{gname}.jsonl")
        scored = []
        if os.path.exists(p):
            for raw_row in load_jsonl(p):
                s_row = score_row(raw_row, key, pool_truth)
                s_row["no_model_answer"] = _no_model_answer(raw_row)
                if "policy_share" not in s_row:
                    s_row["policy_share"] = (1.0 - s_row["coverage_frac"]
                                             if "coverage_frac" in s_row
                                             else _policy_share(raw_row))
                scored.append(s_row)
        v = cell_integrity(scored, exp)
        print(f"  game {gname}: {'ok' if v['ok'] else 'REFUSED'}   model "
              f"answered {v['answered']}/{v['expected']}   fragments placed by "
              f"policy {v['policy_share']:.1%}")
        if v["missing"]:
            more = " ..." if len(v["missing"]) > 8 else ""
            print(f"    no model answer: {', '.join(v['missing'][:8])}{more}")
        if v["policy_heavy"]:
            more = " ..." if len(v["policy_heavy"]) > 8 else ""
            print(f"    model placed under {1 - POLICY_CAP:.0%} of fragments: "
                  f"{', '.join(v['policy_heavy'][:8])}{more}")
        if not v["ok"]:
            refused.add(gname)
    return refused


def report(out_dir, key, pool_truth, withhold=frozenset()):
    rows = []
    for g in ("O", "L", "J"):
        p = os.path.join(out_dir, f"{g}.jsonl")
        if os.path.exists(p):
            rows += [score_row(r, key, pool_truth) for r in load_jsonl(p)
                     if not _no_model_answer(r)]

    O = [r for r in rows if r["game"] == "O" and not r.get("malformed")]
    Om = [r for r in rows if r["game"] == "O" and r.get("malformed")]
    L = [r for r in rows if r["game"] == "L"]
    J = [r for r in rows if r["game"] == "J"]
    # A refused game prints no mean at all. integrity_gate has said why, and a
    # number printed underneath a warning still gets copied into a table.
    if "O" in withhold:
        O, Om = [], []
    if "L" in withhold:
        L = []
    if "J" in withhold:
        J = []

    print("\n" + "=" * 74)
    print(" THREE ATTACK CONDITIONS, SAME CORPUS, SAME MODEL")
    print("=" * 74)
    if O:
        t = [r["tau"] for r in O]
        print(f"\nGAME O  (oracle linkage: membership given, order only)")
        print(f"  scored {len(O)}/{len(O)+len(Om)} documents   malformed {len(Om)}")
        if O and "longest_run" in O[0]:
            n = len(O)
            print(f"  recovered: {sum(r['exact_positions'] for r in O)}"
                  f"/{sum(r['n'] for r in O)} fragments exactly placed   "
                  f"mean shift {sum(r['mean_shift'] for r in O)/n:.1f}   "
                  f"longest intact run {sum(r['longest_run'] for r in O)/n:.1f}"
                  f" of {sum(r['n'] for r in O)/n:.1f} "
                  f"({sum(r['run_fraction'] for r in O)/n:.0%})")
        print(f"  tau  mean {np.mean(t):+.4f}   median {np.median(t):+.4f}   "
              f"min {min(t):+.3f}  max {max(t):+.3f}")

    for name, S in (("GAME L  (grouping only, no ordering asked)", L),
                    ("GAME J  (joint: membership AND order, nothing given)", J)):
        if not S:
            continue
        print(f"\n{name}")
        print(f"  pools scored {len(S)}")
        print(f"  linkage F1   mean {np.mean([r['f1'] for r in S]):.4f}   "
              f"baseline {np.mean([r['baseline'] for r in S]):.4f}   "
              f"advantage {np.mean([r['advantage'] for r in S]):+.4f}")
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
                  f"   baseline {np.mean([r['joint_baseline'] for r in S]):.4f}"
                  f"   advantage {np.mean([r['joint_advantage'] for r in S]):+.4f}")
            q, n_undef = micro_q(S)
            print(f"  direction accuracy      q_micro "
                  f"{('%.4f' % q) if q is not None else 'undefined'}"
                  f"   (K=0 in {n_undef}/{len(S)} pools)")
            tj = [r["tau_in_matched"] for r in S if not np.isnan(r["tau_in_matched"])]
            print(f"  tau in matched groups   mean {np.mean(tj):+.4f}  (n={len(tj)} pools)")
            print(f"  records recovered EXACTLY (membership and order): "
                  f"{sum(r['exact_records'] for r in S)}/{sum(r['n_groups_true'] for r in S)}"
                  f"  ({np.mean([r['exact_rate'] for r in S]):.1%})")

    if O and J:
        tj = [r["tau_in_matched"] for r in J if not np.isnan(r["tau_in_matched"])]
        if tj:
            # Reported, NOT interpreted as 'how much of the defence is
            # linkage'. O and J are differently prompted and on different
            # scales, so the difference carries task coupling too. O is put
            # on the joint scale as (1+tau)/2 for a like-for-like read;
            # q_micro above is the actual linkage-vs-ordering split.
            o_tau = np.mean([r['tau'] for r in O])
            print(f"\nREFERENCE  membership-oracle tau {o_tau:+.4f} "
                  f"= {(1 + o_tau) / 2:.4f} on the joint scale;  "
                  f"joint tau-in-matched {np.mean(tj):+.4f}")
            print("  Not a ceiling, not a decomposition -- see q_micro.")
    if L and J:
        print(f"COST OF ASKING FOR ORDER  linkage advantage "
              f"{np.mean([r['advantage'] for r in L]):+.4f} (L) -> "
              f"{np.mean([r['advantage'] for r in J]):+.4f} (J)")
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
    ap.add_argument("--repair", type=int, default=1,
                    help="repair rounds for an incomplete or malformed answer. "
                         "0 reproduces the old no-repair behaviour, which "
                         "dropped 12 of 32 game-O units on the free-tier probe "
                         "and never once produced a complete J partition.")
    ap.add_argument("--passes", type=int, default=3,
                    help="re-attempt units the model never answered, with "
                         "backoff. A quota stop ends the run early; re-running "
                         "the same command resumes it.")
    ap.add_argument("--allow-partial", action="store_true",
                    help="print means for a game that failed the integrity "
                         "gate, as DIAGNOSTICS. Never for a reported result.")
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
        stop = False
        for g in a.games:
            if stop:
                break
            units = o_units if g == "O" else pools
            out_g = os.path.join(a.out_dir, f"{g}.jsonl")
            for p in range(1, a.passes + 1):
                print()
                print(f"[game {g}] {len(units)} units   pass {p}/{a.passes}")
                failed, quota_hit = run_game(
                    client, g, units, model, out_g, a.seed,
                    pause=a.pause, tpm_limit=a.tpm_limit,
                    max_retries=a.repair)
                if not failed:
                    break
                if p == a.passes:
                    stop = quota_hit
                    break
                # A quota stop is usually a per-MINUTE burst, not the daily
                # cap: on the free tier a document-sized request fit again
                # minutes after the refusal. Cool down and retry rather than
                # abandoning the run. A genuine daily cap fails every pass and
                # still ends REFUSED -- correct, just a few minutes slower.
                wait = 90 if quota_hit else 60 * p
                print(f"  {len(failed)} unit(s) without a model answer -- "
                      f"retrying them in {wait}s")
                time.sleep(wait)
        print("\n" + preflight_summary())

    games_checked = (list(a.games) if not a.score_only else
                     [g for g in ("O", "L", "J")
                      if os.path.exists(os.path.join(a.out_dir, f"{g}.jsonl"))])
    expected = {g: [u[0] for u in (o_units if g == "O" else pools)]
                for g in games_checked}
    refused = integrity_gate(a.out_dir, key, pool_truth, expected)
    report(a.out_dir, key, pool_truth,
           withhold=frozenset() if a.allow_partial else refused)
    if refused and not a.allow_partial:
        print()
        print(f"REFUSED: game(s) {', '.join(sorted(refused))} -- means withheld. "
              "Re-run the same command to complete the missing units, or pass "
              "--allow-partial to see the numbers as diagnostics only.")
        sys.exit(1)


if __name__ == "__main__":
    main()
