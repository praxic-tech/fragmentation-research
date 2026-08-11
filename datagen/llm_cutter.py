"""
llm_cutter.py — the `llm-cut` strategy: the model chooses its own cut points.

This is the one grid cell where the DEFENDER is an LLM. Every other strategy
imposes a rule (cut everywhere, cut randomly, cut at discourse links); here the
model is shown a document and asked where to cut it to make reassembly hardest,
choosing both the positions and — implicitly — the granularity.

Same interface and I/O contract as prose_cutter.py:

    cut(text, ...) -> list[str]
    cut_corpus(raw_path, out_dir, ...) -> prose_fragments.jsonl + prose_answer_key.jsonl

THE MODEL RETURNS INDICES, NOT TEXT
-----------------------------------
The document is pre-split into clause units (the finest linguistic granularity
available) and shown numbered. The model returns a JSON array of unit indices to
cut BEFORE. Two reasons this matters:

  * **Content integrity.** If the model re-emitted the text it could paraphrase,
    drop, or normalise it, and the corpus would silently stop matching
    `prose_raw.jsonl`. Returning indices makes corruption structurally
    impossible — fragments are always exact joins of the original units.
  * **Cost.** Output is a short integer list rather than a full copy of the
    document. A 40-sentence document costs a few hundred output tokens instead
    of several thousand, which is what keeps this cell affordable.

Choosing at clause boundaries lets the model land anywhere from clause
granularity (cut at every index) to multi-sentence chunks (cut rarely), so
"the model picks the granularity" is real rather than nominal.

CACHING
-------
Every decision is cached to `--cache` keyed by record_id, and the cache is
consulted before any API call. Re-running is free; a crashed run resumes.
Use `--limit` to cut a sample before committing to all 500 documents.

Usage (from the repo root):
    # 20-document sample first — check the cost and the cut profile
    python datagen/llm_cutter.py --out-dir results/grid/llm_cut --limit 20

    # then the rest; cached documents are skipped
    python datagen/llm_cutter.py --out-dir results/grid/llm_cut

    # rebuild fragments from cache alone, no API calls, no key needed
    python datagen/llm_cutter.py --out-dir results/grid/llm_cut --offline

Then profile where it actually cut:
    python analysis/cut_position_profile.py --cell results/grid/llm_cut
"""

import argparse
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from prose_cutter import (            # noqa: E402  — one tokenizer for the whole grid
    DEFAULT_RAW,
    ROOT,
    _split_clauses,
    load_jsonl,
)

DEFAULT_CACHE = os.path.join(ROOT, "results", "llm_cut_decisions.jsonl")
DEFAULT_MODEL = "claude-sonnet-5"
BASE_URL      = "https://api.anthropic.com/v1/"

# A free-tier provider drops in here — the OpenAI-compatible surface is the same.
# Groq: base_url https://api.groq.com/openai/v1, model llama-3.3-70b-versatile.
# `thinking` is Anthropic-only and is skipped automatically off that host.
PROVIDERS = {
    "anthropic": ("https://api.anthropic.com/v1/", "claude-sonnet-5"),
    "groq":      ("https://api.groq.com/openai/v1", "llama-3.3-70b-versatile"),
}
PAUSE_SECONDS = 1

# INTERACTIVE pricing (per million tokens). cost_model_v2 uses 1.0/5.0 because
# it assumes the Batches API and its 50% discount; this script calls the
# synchronous endpoint, so it pays full freight. Getting this wrong understates
# every projection by exactly 2x.
IN_PER_M, OUT_PER_M = 2.0, 10.0


class SpendMeter:
    """Running token/cost accounting with a hard stop.

    RUN_PLAN section 9 asks for a spend meter; this is it, scoped to one script.
    check_budget() is called BEFORE each request using the observed mean cost so
    far, so the cap is never discovered after it has already been exceeded.
    """

    def __init__(self, budget=None):
        self.budget = budget
        self.in_tok = 0
        self.out_tok = 0
        self.calls = 0

    @property
    def cost(self):
        return self.in_tok / 1e6 * IN_PER_M + self.out_tok / 1e6 * OUT_PER_M

    def record(self, usage):
        if usage is None:
            return
        self.in_tok += getattr(usage, "prompt_tokens", 0) or 0
        self.out_tok += getattr(usage, "completion_tokens", 0) or 0
        self.calls += 1

    def would_exceed(self):
        """True if one more average-cost call would break the budget."""
        if self.budget is None or self.calls == 0:
            return False
        return self.cost + (self.cost / self.calls) > self.budget

    def summary(self):
        per = self.cost / self.calls if self.calls else 0.0
        return (f"  spend: ${self.cost:.4f} over {self.calls} calls "
                f"(${per:.4f}/doc)  in {self.in_tok:,} tok / out {self.out_tok:,} tok")

# ── prompt variants ──────────────────────────────────────────────────────────
# Versioned, not replaced. v1 produced the profile in docs/llm_cut_profile.md;
# deleting it would make that finding unreproducible. Pick with --prompt.

_TAIL = """
Units:
{units}

Return ONLY a JSON array of integers between 1 and {max_idx}, in ascending order. No explanation, no markdown."""

PROMPTS = {
    # Baseline. Measured: never cuts mid-clause, lands coarser than a sentence,
    # leaves 6x more dangling links exposed than a fixed 12-token window.
    "v1": """You are protecting this document by cutting it into fragments. The fragments will be shuffled and an adversary will try to put them back in order.

The document is split into {n} numbered units below. Choose which unit indices to cut BEFORE, so that each fragment is one or more consecutive units. Index 0 is the start of the document and is always a cut; do not include it.

Cut wherever reassembly would be hardest. You choose how many cuts to make and therefore how large the fragments are — few large fragments or many small ones, whichever resists reordering better.""" + _TAIL,

    # v1 cut like an editor: it preserved grammatical units and left sentence
    # openings intact, which is exactly what a reassembler exploits. v2 states
    # the adversary's method and removes the implicit requirement to be tidy.
    "v2-adversarial": """You are protecting this document by cutting it into fragments. The fragments will be shuffled and an adversary will try to restore their original order.

The document is split into {n} numbered units below. Choose which unit indices to cut BEFORE. Index 0 is the start of the document and is always a cut; do not include it.

How the adversary wins: they look for fragments that obviously follow one another. A fragment that begins a new sentence, or that starts with a connective ("however", "therefore") or a pronoun whose referent sits in another fragment, tells them where it belongs.

So do NOT cut only at tidy sentence starts. Fragments do not need to be grammatical, readable, or self-contained — a fragment that ends mid-thought and resumes mid-thought is harder to place, not easier. Prefer boundaries that split a continuing idea over boundaries that close one cleanly.

Make the fragments small and uniform enough that no single one stands out as an obvious opening or ending.""" + _TAIL,
}


# ── model call ───────────────────────────────────────────────────────────────

def make_client(provider="anthropic"):
    from dotenv import load_dotenv
    from openai import OpenAI
    load_dotenv(os.path.join(ROOT, "apikey.env"))
    load_dotenv(os.path.join(ROOT, ".env"))
    base_url, _ = PROVIDERS[provider]
    # Provider-specific key first, so two providers can coexist in one env file.
    key = (os.environ.get(f"{provider.upper()}_API_KEY")
           or os.environ.get("LLM_API_KEY")
           or os.environ.get("API_KEY"))
    if not key:
        sys.exit(f"ERROR: no API key for {provider}. Set {provider.upper()}_API_KEY "
                 f"(or LLM_API_KEY / API_KEY) in apikey.env or .env at the repo root.")
    return OpenAI(base_url=base_url, api_key=key)


def _parse_indices(raw, n_units):
    """Pull a JSON integer array out of the reply and make it usable.

    Anything out of range, duplicated, or unordered is repaired rather than
    trusted — a malformed reply must not silently produce a corrupt cell.
    """
    match = re.search(r"\[.*?\]", raw, re.S)
    if not match:
        raise ValueError(f"no JSON array in reply: {raw[:200]!r}")
    values = json.loads(match.group(0))
    clean = sorted({int(v) for v in values if isinstance(v, (int, float))
                    and 1 <= int(v) < n_units})
    return clean


class ZeroAnswerError(RuntimeError):
    """The call spent its whole output budget on reasoning and returned no answer.

    RUN_PLAN section 9 asks for a zero-answer detector; this is it. Worth its own
    exception type because it is billed exactly like a successful call and is
    otherwise indistinguishable from a parse failure — which is how it went
    unnoticed here until the spend meter showed money leaving with nothing
    written.
    """


# Sonnet 5 rejects `thinking.budget_tokens` (400). Adaptive thinking is ON by
# default and, on this task, consumed a 2,000-token cap without emitting an
# answer. Disabling it is what makes this cell affordable.
THINKING = {
    "off":      {"thinking": {"type": "disabled"}},
    "adaptive": {},
}


def split_units(text, kind="clause"):
    """Candidate cut positions offered to the model.

    clause — linguistic units. Cheap, but the model CANNOT cut mid-clause, so
             the "never cuts mid-clause" result is partly a property of this
             choice rather than purely of the model's judgement.
    word   — every whitespace token is a candidate. This is what actually lets
             the model break a grammatical unit. Costs ~2x input, since every
             token carries an index.
    """
    if kind == "clause":
        return _split_clauses(text)
    if kind == "word":
        return re.sub(r"\s+", " ", text).strip().split()
    raise ValueError(f"unknown unit kind {kind!r}; choose clause or word")


def request_cut_points(client, units, model, max_tokens=4000, meter=None,
                       thinking="off", prompt="v1", provider="anthropic"):
    """Ask the model where to cut. Returns (indices, usage)."""
    numbered = "\n".join(f"{i}: {u}" for i, u in enumerate(units))
    body = PROMPTS[prompt].format(n=len(units), units=numbered,
                                  max_idx=len(units) - 1)

    # `thinking` is an Anthropic parameter; sending it to another host 400s.
    extra = THINKING.get(thinking, {}) if provider == "anthropic" else {}

    reply = client.chat.completions.create(
        model=model,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": body}],
        extra_body=extra,
    )
    usage = getattr(reply, "usage", None)
    if meter is not None:
        meter.record(usage)          # record BEFORE parsing — a failed parse still bills

    content = (reply.choices[0].message.content or "").strip()
    if not content:
        out = getattr(usage, "completion_tokens", 0) or 0
        raise ZeroAnswerError(
            f"empty answer after {out} output tokens "
            f"(cap {max_tokens}) — all reasoning, no answer. "
            f"Raise --max-tokens or use --thinking off."
        )
    return _parse_indices(content, len(units)), usage


# ── strategy ─────────────────────────────────────────────────────────────────

def assemble(units, cut_points):
    """Join units into fragments, cutting before each index in cut_points."""
    if not units:
        return []
    fragments, current = [], [units[0]]
    for i in range(1, len(units)):
        if i in cut_points:
            fragments.append(" ".join(current))
            current = [units[i]]
        else:
            current.append(units[i])
    fragments.append(" ".join(current))
    return fragments


def cut(text, client=None, model=DEFAULT_MODEL, cut_points=None,
        prompt="v1", units_kind="clause", provider="anthropic", **_):
    """llm-cut. Pass cut_points to replay a cached decision without an API call."""
    units = split_units(text, units_kind)
    if cut_points is None:
        if client is None:
            raise ValueError("llm-cut needs either a client or cached cut_points")
        cut_points, _ = request_cut_points(client, units, model, prompt=prompt,
                                           provider=provider)
    return assemble(units, set(cut_points))


# ── corpus runner ────────────────────────────────────────────────────────────

def cache_key(record_id, model, prompt, units):
    """A cached decision is only valid for the exact (document, model, prompt,
    unit-type) it was produced under.

    Keying on record_id alone would silently replay v1/Sonnet decisions under a
    new prompt or a different provider — the run would look free and the
    comparison would be meaningless. Older cache rows have no model/prompt
    fields; they are treated as v1 + claude-sonnet-5 + clause, which is what they
    were."""
    return (record_id, model, prompt, units)


def load_cache(path):
    if not os.path.exists(path):
        return {}
    out = {}
    for r in load_jsonl(path):
        out[cache_key(r["record_id"],
                      r.get("model",  "claude-sonnet-5"),
                      r.get("prompt", "v1"),
                      r.get("units",  "clause"))] = r
    return out


def append_cache(path, row):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")


def cut_corpus(raw_path, out_dir, cache_path=DEFAULT_CACHE,
               model=DEFAULT_MODEL, limit=None, offline=False, budget=None,
               thinking="off", max_tokens=4000, prompt="v1", units_kind="clause",
               provider="anthropic"):
    os.makedirs(out_dir, exist_ok=True)
    records = load_jsonl(raw_path)
    if limit:
        records = records[:limit]

    cache = load_cache(cache_path)
    meter = SpendMeter(budget)
    print(f"[llm-cut] provider={provider} model={model} prompt={prompt} "
          f"units={units_kind} thinking={thinking}")
    need = [r for r in records
            if cache_key(r["record_id"], model, prompt, units_kind) not in cache]
    client = None
    if not offline and need:
        client = make_client(provider)

    frag_path = os.path.join(out_dir, "prose_fragments.jsonl")
    key_path  = os.path.join(out_dir, "prose_answer_key.jsonl")

    total_frags, frag_counts, skipped, called = 0, [], 0, 0

    with open(frag_path, "w", encoding="utf-8") as ff, \
         open(key_path,  "w", encoding="utf-8") as kf:

        for rec in records:
            rid   = rec["record_id"]
            units = split_units(rec["text"], units_kind)
            ck    = cache_key(rid, model, prompt, units_kind)

            if ck in cache:
                cut_points = cache[ck]["cut_points"]
            elif offline:
                skipped += 1
                continue
            elif meter.would_exceed():
                print(f"  [budget] stopping before {rid} — ${meter.cost:.4f} spent, "
                      f"one more call would pass the ${budget:.2f} cap")
                skipped += 1
                continue
            else:
                try:
                    cut_points, usage = request_cut_points(
                        client, units, model, max_tokens=max_tokens,
                        meter=meter, thinking=thinking, prompt=prompt,
                        provider=provider)
                except ZeroAnswerError as e:
                    print(f"  [ZERO-ANSWER] {rid}: {e}")
                    skipped += 1
                    continue
                except Exception as e:
                    print(f"  [warn] {rid}: {e} — skipped, will retry next run")
                    skipped += 1
                    continue
                append_cache(cache_path, {
                    "record_id":  rid,
                    "model":      model,
                    "prompt":     prompt,
                    "units":      units_kind,
                    "n_units":    len(units),
                    "cut_points": cut_points,
                    "in_tokens":  getattr(usage, "prompt_tokens", None),
                    "out_tokens": getattr(usage, "completion_tokens", None),
                })
                called += 1
                print(f"  {rid}: {len(units)} units -> {len(cut_points)} cuts   "
                      f"[${meter.cost:.4f} running]")
                time.sleep(PAUSE_SECONDS)

            fragments = assemble(units, set(cut_points))
            frag_counts.append(len(fragments))

            order = []
            for position, text in enumerate(fragments):
                fid = f"{rid}_frag_{position:03d}"
                order.append(fid)
                ff.write(json.dumps({"record_id":   rid,
                                     "fragment_id": fid,
                                     "text":        text}) + "\n")
                total_frags += 1
            kf.write(json.dumps({"record_id": rid, "order": order}) + "\n")

    if not frag_counts:
        print(f"[llm-cut] NOTHING WRITTEN from {len(records)} records "
              f"({skipped} skipped).")
        if meter.calls:
            print(meter.summary())
            print("  ^ these calls were billed and produced no usable output.")
        return

    print(f"[llm-cut x model's own]  {len(frag_counts)} records -> {total_frags} fragments  "
          f"(min={min(frag_counts)}, max={max(frag_counts)}, "
          f"mean={sum(frag_counts)/len(frag_counts):.1f})")
    print(f"  API calls this run: {called}   from cache: {len(frag_counts) - called}"
          f"   skipped: {skipped}")
    if meter.calls:
        print(meter.summary())
        per = meter.cost / meter.calls
        print(f"  projected for all 500 docs: ${per * 500:.2f} interactive, "
              f"${per * 250:.2f} batched")
    print(f"  wrote: {frag_path}")
    print(f"  wrote: {key_path}")
    print(f"  cache: {cache_path}")


def parse_args():
    p = argparse.ArgumentParser(description="Cut a prose corpus by asking an LLM where to cut.")
    p.add_argument("--raw", default=DEFAULT_RAW)
    p.add_argument("--out-dir", required=True)
    p.add_argument("--cache", default=DEFAULT_CACHE,
                   help="cut decisions, reused across runs (default results/llm_cut_decisions.jsonl)")
    p.add_argument("--provider", default="anthropic", choices=list(PROVIDERS),
                   help="groq is the free-tier option; model defaults follow it")
    p.add_argument("--model", default=None,
                   help="overrides the provider default")
    p.add_argument("--prompt", default="v1", choices=list(PROMPTS),
                   help="v1 is the measured baseline; v2-adversarial tells the "
                        "model how the attacker wins and drops the tidiness constraint")
    p.add_argument("--units", default="clause", choices=["clause", "word"],
                   help="'word' is what allows mid-clause cuts at all (~2x input cost)")
    p.add_argument("--limit", type=int, default=None,
                   help="only cut the first N documents — use this before committing budget")
    p.add_argument("--offline", action="store_true",
                   help="rebuild from cache only; never call the API")
    p.add_argument("--budget", type=float, default=None,
                   help="hard USD cap; stops before the call that would exceed it")
    p.add_argument("--thinking", default="off", choices=["off", "adaptive"],
                   help="adaptive thinking burns the output cap without answering "
                        "on this task; 'off' is the default for that reason")
    p.add_argument("--max-tokens", type=int, default=4000)
    return p.parse_args()


def main():
    args = parse_args()
    model = args.model or PROVIDERS[args.provider][1]
    cut_corpus(args.raw, args.out_dir, cache_path=args.cache,
               model=model, limit=args.limit, offline=args.offline,
               budget=args.budget, thinking=args.thinking,
               max_tokens=args.max_tokens, prompt=args.prompt,
               units_kind=args.units, provider=args.provider)


if __name__ == "__main__":
    main()
