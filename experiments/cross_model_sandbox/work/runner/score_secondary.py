"""Write the preregistered SECONDARY "answered units only" score. NO MODEL CALLS.

    python -I work/runner/score_secondary.py gemma-4-12b

For a cell refused under the preregistered rule (a unit over joint_game.POLICY_CAP)
which the frozen gate did not flag (Game J: the gate reads 1 - coverage_frac,
computed after the completion policy has filled the gaps, never the recorded
repair.policy_share; see logs/RUNLOG.md 2026-11-13). Does exactly what the
runner's refusal path does (runner.Runner.score): the frozen batch_game.score on
the same waves with allow_partial=True, into final_headlineJ_answered_units_only/,
with the same SECONDARY header. The scorer is not changed and not re-implemented.
"""
import contextlib
import io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import runner as R                                               # noqa: E402
import batch_game                                                # noqa: E402

SANDBOX = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main(slug):
    cfg = R.CONFIGS[slug]
    raw = os.path.join(SANDBOX, "raw", slug)
    res = os.path.join(SANDBOX, "results", slug)
    used = json.load(open(os.path.join(res, "final_headlineJ", "verdict.json"), encoding="utf-8"))
    batch_game.MODEL_MAX_OUTPUT = cfg["budget"]                  # as the runner sets it
    waves = []
    for tag, files in used["waves"]:
        spec = (json.load(open(R.HEADLINE_SPEC, encoding="utf-8")) if tag == "final-headlineJ"
                else json.load(open(os.path.join(raw, f"{tag}.spec.json"), encoding="utf-8")))
        assert spec["tag"] == tag, (spec["tag"], tag)
        waves.append((spec, [os.path.join(raw, f) for f in files]))
    out2 = os.path.join(res, "final_headlineJ_answered_units_only")
    buf2 = io.StringIO()
    with contextlib.redirect_stdout(buf2):
        batch_game.score(waves, out2, allow_partial=True)
    with open(os.path.join(out2, "REPORT.txt"), "w", encoding="utf-8") as fh:
        fh.write("SECONDARY: answered units only (allow_partial=True). The integrity gate "
                 "refused this game; that refusal is the primary result.\n"
                 "(Refused under the preregistered rule: units over joint_game.POLICY_CAP by their "
                 "recorded repair.policy_share. The frozen gate's own check missed them; see "
                 "logs/RUNLOG.md, 2026-11-13, and ../PRIMARY_RESULT.md.)\n\n" + buf2.getvalue())
    print(f"secondary (answered units only) -> {out2}")


if __name__ == "__main__":
    main(sys.argv[1])
