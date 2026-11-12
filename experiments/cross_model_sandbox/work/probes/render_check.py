"""Check that a spec's rendered prompts do not depend on the day they are run.

No generation: llama-server /apply-template and /tokenize only. Each frozen
request is one user message, request["prompt"] verbatim.

Checks:
  1. render every request twice with the same kwargs: identical;
  2. render with a different `current_date`: differs only on the "Current date:" line,
     so the kwarg fully controls the date (nothing else is time-dependent);
  3. render without `current_date`: the date line shows the sentinel
     "PINNED-DATE-MISSING" (the caller refuses to send such a prompt);
  4. no rendered prompt contains today's date unless it is the pinned date.
Writes one SHA-256 per rendered prompt, for comparison on the run day.

usage: python -I work/probes/render_check.py SPEC BASE_URL KWARGS_JSON OUT_JSON [MUST_CONTAIN]

Checks 2 and 3 run only when KWARGS has `current_date` (gpt-oss). For a template
with no date (Gemma) they are skipped, check 4 still runs, and MUST_CONTAIN (e.g.
"<|think|>") must appear in every render.
"""
import datetime
import hashlib
import json
import sys
import urllib.error
import urllib.request


def post(base, path, body):
    req = urllib.request.Request(base + path, data=json.dumps(body).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as r:
        return json.loads(r.read().decode("utf-8"))


def render(base, prompt, kwargs):
    return post(base, "/apply-template", {"messages": [{"role": "user", "content": prompt}],
                                          "chat_template_kwargs": kwargs})["prompt"]


def main():
    spec_path, base, kwargs_json, out = sys.argv[1:5]
    must = sys.argv[5] if len(sys.argv) > 5 else None
    kwargs = json.loads(kwargs_json)
    dated = "current_date" in kwargs
    pinned = kwargs.get("current_date")
    other = dict(kwargs, current_date="2031-03-17")
    today = datetime.date.today().isoformat()
    spec = json.load(open(spec_path, encoding="utf-8"))
    rows, ok = [], True
    for r in spec["requests"]:
        a = render(base, r["prompt"], kwargs)
        b = render(base, r["prompt"], kwargs)
        same = a == b
        if dated:
            c = render(base, r["prompt"], other)
            diff = [(x, y) for x, y in zip(a.split("\n"), c.split("\n")) if x != y]
            only_date = (len(a.split("\n")) == len(c.split("\n")) and len(diff) == 1
                         and diff[0] == (f"Current date: {pinned}", "Current date: 2031-03-17"))
        else:
            only_date = None
        has_must = must is None or must in a
        no_today = today == pinned or today not in a
        verbatim = r["prompt"] in a
        toks = len(post(base, "/tokenize", {"content": a, "add_special": True,
                                            "parse_special": True})["tokens"])
        ok &= same and (only_date or not dated) and no_today and verbatim and has_must
        rows.append({"unit": r["unit"], "sha256": hashlib.sha256(a.encode("utf-8")).hexdigest(),
                     "tokens": toks, "repeat_identical": same, "only_date_line_differs": only_date,
                     "prompt_verbatim": verbatim, "contains_required": has_must})
    if dated:
        missing = render(base, "x", {k: v for k, v in kwargs.items() if k != "current_date"})
        sentinel_shown = "Current date: PINNED-DATE-MISSING\n" in missing
        ok &= sentinel_shown
    else:
        sentinel_shown = None
    summary = {"spec": spec["tag"], "n": len(rows), "kwargs": kwargs, "today": today,
               "all_repeat_identical": all(x["repeat_identical"] for x in rows),
               "all_only_date_line_differs": (all(x["only_date_line_differs"] for x in rows)
                                              if dated else None),
               "required_substring": must,
               "all_contain_required": all(x["contains_required"] for x in rows),
               "all_prompts_verbatim": all(x["prompt_verbatim"] for x in rows),
               "missing_current_date_renders_sentinel": sentinel_shown,
               "max_tokens": max(x["tokens"] for x in rows), "ok": bool(ok)}
    json.dump({"summary": summary, "rows": rows}, open(out, "w", encoding="utf-8"), indent=1)
    print(json.dumps(summary, indent=1))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
