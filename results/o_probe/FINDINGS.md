# Free-tier game-O probe: is the grid worth running?

Five cut strategies, the SAME 8 documents, one attacker model
(qwen/qwen3.8-27b, Groq free tier), repair on so every cell scores 8/8.
Total cost: $0.11, all of it the llm-cut *defender* calls.

## Kendall tau per document (tau / fragments)

```
doc                  random       semantic  coherence-sev   subject-verb        llm-cut
prose_0002     -0.103/30      +0.724/30      +0.877/24      +0.324/55      +0.672/28
prose_0003     +0.301/30      +0.347/30      +0.490/30      +0.410/54      -0.143/15
prose_0005     +0.766/19      +0.719/19      +0.647/17      +0.099/30      +0.564/13
prose_0007     +0.886/21      +0.914/21      +0.952/21      +0.828/31      +1.000/7
prose_0014     +0.039/30      +0.802/30      +0.695/29      +0.367/52      +0.944/9
prose_0015     +0.430/27      +0.658/27      +0.766/27      +0.392/48      +0.897/17
prose_0024     +0.311/27      +0.897/27      +0.895/26      +0.637/46      +0.801/19
prose_0025     +0.863/27      +0.499/27      +0.557/26      +0.505/40      +0.922/18

MEAN           +0.437/26      +0.695/26      +0.735/25      +0.445/44      +0.707/16
```

## 1. The strategies separate, and the spread is large

0.30 tau between the best and worst. That is not a subtle effect and it is
visible at n=8 on a free model. **random and subject-verb resist ordering;
semantic, coherence-sever and llm-cut do not.**

The two winners are the two that ignore meaning. random cuts without regard to
content; subject-verb cuts at grammatical joints. The three that lose all cut at
places a reader would recognise as natural, which is what leaves each fragment
readable enough to place.

## 2. The confound is NOT what killed it

random and semantic produce *identical* fragment counts -- 26/doc, same
documents, same granularity -- and differ by 0.26 tau. Fragment count cannot
explain that, so at least one real boundary-rule effect exists.

Across cells fragment count still correlates negatively with tau
(r = -0.666, p = 0.220, n = 5 cells), so subject-verb's result remains partly
a size effect and the granularity-matched probes are still needed to separate
them. But random-vs-semantic is a clean within-size contrast and it holds.

## 3. llm-cut is the interesting cell

The LLM defender cuts to 16 fragments/doc -- the fewest of any strategy, half of
random's -- and is the EASIEST to reconstruct (+0.707), including one document
recovered perfectly (+1.000). Asked to defend, it produced few, large, coherent
pieces. That is the intuition of an editor, not an adversary, and it is a result
worth reporting rather than a cell worth cutting.

## 4. THE METHOD FINDING: without repair the ranking is an artifact

Before repair was wired in, each cell scored only the documents it happened to
answer cleanly, and the cells answered *different* documents. Re-running the
same cells with repair moves the numbers by wildly different amounts:

```
                  survivors only        all 8 docs        shift
random            +0.7434 (n=5)    ->   +0.4366        -0.3068
semantic          +0.6497 (n=7)    ->   +0.6952        +0.0455
coherence-sever   +0.7378 (n=6)    ->   +0.7349        -0.0029
subject-verb      +0.3782 (n=2)    ->   +0.4451        +0.0669
```

random looked like the WEAKEST defence at +0.74 and is actually among the
strongest at +0.44. The three documents it dropped were the three it defended
best. Any grid run without repair would have published a reversed ranking with
no visible symptom.

## Verdict

**The grid is worth running.** The effect is large, it survives a within-size
control, and one cell (llm-cut) is a finding on its own.

Do not run it without repair.

Caveats: n=8 documents, one free model, sentence granularity only. These are
directional, not the paper's numbers.
