"""Make a copy of gpt-oss-20b's embedded chat template with the date fixed.

The GGUF's embedded template writes "Current date: " + strftime_now("%Y-%m-%d"),
so the system message changes with the day of the run. This copies the template
exactly and changes only that call: the date now comes from the
chat_template_kwargs key `current_date`. If it is missing the line reads
"Current date: PINNED-DATE-MISSING", which the caller refuses to send.

usage: python -I work/templates/make_gpt_oss_fixed_date.py PROPS_JSON
  PROPS_JSON: the /props response of llama-server running the pinned GGUF.
Writes work/templates/gpt-oss-20b.embedded.jinja and gpt-oss-20b.fixed-date.jinja.
"""
import hashlib
import json
import sys
from pathlib import Path

BS = chr(92)  # backslash, written this way so no shell or editor can alter it
OLD = '{{- "Current date: " + strftime_now("%Y-%m-%d") + "' + BS + 'n' + BS + 'n" }}'
# A missing date renders a sentinel instead of raising: llama-server test-renders
# the template at startup with no kwargs and rejects a template that raises. The
# caller asserts every rendered prompt contains "Current date: <pinned date>",
# so a request without the kwarg is refused before it is sent.
SENTINEL = "PINNED-DATE-MISSING"
NEW = ('{%- if current_date is not defined %}'
       '{%- set current_date = "' + SENTINEL + '" %}'
       '{%- endif %}' + "\n    "
       '{{- "Current date: " + current_date + "' + BS + 'n' + BS + 'n" }}')

here = Path(__file__).resolve().parent
t = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))["chat_template"]
assert t.count(OLD) == 1, f"expected exactly one date call, found {t.count(OLD)}"
p = t.replace(OLD, NEW)
assert "strftime" not in p and "now(" not in p
for name, s in [("gpt-oss-20b.embedded.jinja", t), ("gpt-oss-20b.fixed-date.jinja", p)]:
    (here / name).write_bytes(s.encode("utf-8"))
    print(name, len(s), hashlib.sha256(s.encode("utf-8")).hexdigest())
