QUARANTINED 2026-09-10. Do not score these files.

Five free-tier game-O cells run after the Groq daily quota ran out.
call_model raised once its 429 backoff gave up; run_with_repair caught
the exception and treated it as an empty answer; the completion policy
then supplied the whole order. Those orders were scored as attacks.

Share of fragments placed by our policy rather than the model:
  subject-verb/clause 85.2   coherence-sever/token-window 84.7
  coherence-sever/clause 74.1   semantic/token-window 64.0
  semantic/clause 27.0

Kept as evidence for the fix (NoModelAnswer, the integrity gate).
The cells are re-run from scratch with the fixed code.
