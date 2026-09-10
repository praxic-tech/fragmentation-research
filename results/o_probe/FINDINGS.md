# Free-tier game-O probe — does per-cell O discriminate between strategies?

Four cut strategies, the SAME 8 documents, sentence granularity, one model
(qwen/qwen3.8-27b on the Groq free tier). Cost: $0.

## Per-document Kendall tau

```
doc              random   semantic  coherence  subject-v      frags/doc
prose_0002       +0.664     +0.743     +0.891  malformed    30/30/24/55
prose_0003    malformed     +0.366  malformed  malformed    30/30/30/54
prose_0005       +0.520     +0.673     +0.515  malformed    19/19/17/30
prose_0007       +0.905     +0.724     +0.800     +0.553    21/21/21/31
prose_0014       +0.724     +0.687     +0.626     +0.204    30/30/29/52
prose_0015    malformed  malformed     +0.675  malformed    27/27/27/48
prose_0024    malformed     +0.846     +0.920  malformed    27/27/26/46
prose_0025       +0.903     +0.510  malformed  malformed    27/27/26/40
```

paired, the 2 documents scored in every cell:
    random +0.8144   semantic +0.7056   coherence-sever +0.7128   subject-verb +0.3782

unpaired, as the run prints it (DIFFERENT samples per cell):
    random +0.7434 (n=5)  semantic +0.6497 (n=7)
    coherence-sever +0.7378 (n=6)  subject-verb +0.3782 (n=2)

## Findings

**1. O discriminates, but only for subject-verb, and it is confounded.**
subject-verb scores ~0.35 tau below the other three. It also produces 1.7x the
fragments (31-55 vs 19-30 per document). More pieces is harder to order whatever
the boundary rule does, so this is NOT yet evidence that the cut resists
ordering. It is exactly the confound the granularity-matched probes exist for,
and this probe says those probes are load-bearing rather than optional.

**2. random / semantic / coherence-sever do not separate.** 0.09 tau apart on
2-7 documents. Noise at this sample size.

**3. Malformed rate scales with fragment count, so attrition is not random.**
6/8 malformed at 44.5 frags/doc against 1/8 at 26.4. Documents that are harder
to order are likelier to be dropped, so every cell's tau is biased UP, and the
bias is largest in the cell with the most fragments. subject-verb's +0.378 is
measured on its two easiest survivors: the true figure is probably worse, which
means the one effect the probe found is understated rather than overstated.

**4. THE REAL FINDING: the repair protocol is not wired into the one-shot
attacker.** `harness/repair.py` (`run_with_repair`, `validate`, `finalise`) was
built in Phase 1 for precisely this and `adversaries/joint_game.py` imports none
of it. Two consequences, and they differ by game:

  game O   malformed units are DROPPED from the sample. Upward bias on tau,
           worst where the task is hardest. 12 of 32 units here, 37.5%.
  game J   incomplete answers are still scored, and omission costs recall, so
           the numbers are not inflated -- they are DEPRESSED, and the attacker
           is weaker than it needs to be. Across the whole J pilot, 0 of 14
           units returned a complete valid partition.

J is the headline. An attacker that never once returned a complete answer
understates the risk fragmentation is supposed to defend against, and a reviewer
reads that as the experiment failing to press the attack.

## What this changes

Wire `run_with_repair` into `joint_game.py` before any paid run, and re-measure
the malformed rate. G4's nuisance sizing should then report it per granularity,
because it is clearly a function of fragment count and the grid spans 19-55
fragments per document.

Per-cell O is worth its $6.62 -- but only alongside granularity-matched cells,
otherwise it measures fragment count wearing a strategy's name.
