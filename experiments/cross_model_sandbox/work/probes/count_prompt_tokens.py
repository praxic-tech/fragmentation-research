"""Count a spec's prompts in a model's own tokenizer, through its chat template.

No generation: only llama-server's /apply-template and /tokenize endpoints.
Each frozen request is sent exactly as Sonnet received it: a single user
message whose content is request["prompt"], verbatim. Any system text in the
count is what the model's own chat template inserts (plus an optional system
message, if one is passed with --system).

usage:
  python -I work/probes/count_prompt_tokens.py SPEC BASE_URL OUT_JSON
         [--kwargs JSON] [--system TEXT] [--budget N] [--ctx N]
"""
import argparse
import json
import statistics
import sys
import urllib.request


def post(base, path, body):
    req = urllib.request.Request(base + path, data=json.dumps(body).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as r:
        return json.loads(r.read().decode("utf-8"))


def count(base, prompt, kwargs, system):
    messages = ([{"role": "system", "content": system}] if system else []) + \
               [{"role": "user", "content": prompt}]
    body = {"messages": messages}
    if kwargs:
        body["chat_template_kwargs"] = kwargs
    rendered = post(base, "/apply-template", body)["prompt"]
    assert prompt in rendered, "frozen prompt not found verbatim in rendered template"
    with_special = len(post(base, "/tokenize", {"content": rendered, "add_special": True,
                                               "parse_special": True})["tokens"])
    without = len(post(base, "/tokenize", {"content": rendered, "add_special": False,
                                          "parse_special": True})["tokens"])
    return rendered, with_special, without


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("spec"); ap.add_argument("base"); ap.add_argument("out")
    ap.add_argument("--kwargs", default=None)
    ap.add_argument("--system", default=None)
    ap.add_argument("--budget", type=int, default=32768)
    ap.add_argument("--ctx", type=int, default=65536)
    a = ap.parse_args()
    kwargs = json.loads(a.kwargs) if a.kwargs else None
    spec = json.load(open(a.spec, encoding="utf-8"))
    rows = []
    for i, r in enumerate(spec["requests"]):
        rendered, ws, wo = count(a.base, r["prompt"], kwargs, a.system)
        if i == 0:
            head = rendered[: rendered.index(r["prompt"])]
            tail = rendered[rendered.index(r["prompt"]) + len(r["prompt"]):]
            print("template text before prompt:", repr(head))
            print("template text after prompt: ", repr(tail))
        rows.append({"unit": r["unit"], "prompt_chars": len(r["prompt"]),
                     "tokens_add_special": ws, "tokens_no_special": wo})
    ws = [x["tokens_add_special"] for x in rows]
    summary = {"spec": spec["tag"], "n": len(rows), "kwargs": kwargs, "system": a.system,
               "max": max(ws), "median": statistics.median(ws), "min": min(ws),
               "max_no_special": max(x["tokens_no_special"] for x in rows),
               "budget": a.budget, "ctx": a.ctx,
               "max_plus_budget": max(ws) + a.budget,
               "fits": max(ws) + a.budget <= a.ctx,
               "argmax_unit": rows[ws.index(max(ws))]["unit"]}
    json.dump({"summary": summary, "rows": rows}, open(a.out, "w", encoding="utf-8"), indent=1)
    print(json.dumps(summary, indent=1))
    return 0 if summary["fits"] else 1


if __name__ == "__main__":
    sys.exit(main())
