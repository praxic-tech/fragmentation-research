"""
nsweep_frame.py — the pools of the pool-size sweep (RUN_DECISIONS D22,
POST-HOC EXPLORATORY). Reads the headline spec only; no text, no result.

Every pool is made from the 46 headline pools (runs/final_headlineJ.json, 322
documents, each in exactly one pool), so documents and fragments are the
headline ones and only the number of documents in a pool changes:

    N = 2, 3, 5     part of each headline pool: its members shuffled by
                    random.Random("D22:<pool id>") and the first N taken, so
                    the three sizes are nested. 46 pools each.
    N = 7           the headline pools themselves. Listed for reference; the
                    existing tier 3 headline result is used, nothing is re-run.
    N = 14, 21, 28  2, 3 or 4 consecutive headline pools joined, in pool-id
                    order. 23, 15 and 11 pools; headline pools left over at a
                    size are not used at that size.

Writes data/pools/nsweep_pools.json.

    python runs/nsweep_frame.py
"""

import json
import os
import random

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
SPEC = os.path.join("runs", "final_headlineJ.json")
OUT = os.path.join("data", "pools", "nsweep_pools.json")
PART, JOIN = (2, 3, 5), (2, 3, 4)


def main():
    head = json.load(open(SPEC, encoding="utf-8"))["build"]["pools"]
    assert len(head) == 46 and all(len(m) == 7 for _p, m in head)
    assert len({d for _p, m in head for d in m}) == 322
    assert [p for p, _m in head] == sorted(p for p, _m in head)
    sizes = {}
    order = {}
    for pid, members in head:
        m = list(members)
        random.Random(f"D22:{pid}").shuffle(m)
        order[pid] = m
    for n in PART:
        sizes[n] = [{"pool_id": f"n{n:02d}_{pid}", "members": sorted(order[pid][:n]), "from": [pid]}
                    for pid, _m in head]
    sizes[7] = [{"pool_id": pid, "members": list(m), "from": [pid]} for pid, m in head]
    for k in JOIN:
        n, rows = 7 * k, []
        for i in range(0, len(head) - k + 1, k):
            grp = head[i:i + k]
            rows.append({"pool_id": f"n{n:02d}_{i // k + 1:03d}", "members": sorted(d for _p, m in grp for d in m),
                         "from": [p for p, _m in grp]})
        sizes[n] = rows
    for n, rows in sizes.items():
        assert all(len(r["members"]) == n == len(set(r["members"])) for r in rows)
    frame = {"decision": "RUN_DECISIONS D22 (post-hoc exploratory)", "source": SPEC,
             "sizes": {str(n): rows for n, rows in sorted(sizes.items())},
             "unused_headline_pools": {str(7 * k): [p for p, _m in head[len(head) // k * k:]] for k in JOIN}}
    open(OUT, "w", encoding="utf-8", newline="\n").write(json.dumps(frame, indent=1) + "\n")
    for n, rows in sorted(sizes.items()):
        print(f"N={n:2d}: {len(rows)} pools")
    print("unused:", frame["unused_headline_pools"])
    print("wrote", OUT)


if __name__ == "__main__":
    main()
