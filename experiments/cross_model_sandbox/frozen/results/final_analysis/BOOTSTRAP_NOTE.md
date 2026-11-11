# The bootstrap: what it is and why this study uses it

A write-up aid for the methods section. The frozen choice is RUN_DECISIONS D13.

## What the bootstrap is

We have one sample. Here it is the 46 headline pools, each with an F1_J
score. We want to know how much the mean would move if we could repeat the
whole experiment on fresh pools. We can't, so the bootstrap uses the sample
as a stand-in for the population:

1. Draw 46 pools **with replacement** from the 46 we have. Some pools appear
   twice, some not at all.
2. Compute the statistic on that resample: the mean F1_J, a median, a
   difference between two attackers, or a Spearman ρ.
3. Repeat 10,000 times. That gives 10,000 values of the statistic.
4. The **percentile bootstrap** 95% confidence interval is the 2.5th to
   97.5th percentile of those values (5th to 95th for a 90% interval).

The spread of the resampled statistics estimates the sampling variability of
the real one, without assuming it follows a normal distribution.

## Why it fits this study

- **The independent unit is a pool (game J) or a document (game O)**, not a
  fragment pair (results plan §2). Resampling whole pools keeps every pair
  from one pool together, so the tens of thousands of pairs in a pool are not
  treated as independent evidence. That would make the intervals falsely
  narrow.
- **The scores are bounded and skewed.** F1 lies in [0, 1], and some
  distributions pile up near an edge (Memon-inspired sits near its floor). A
  percentile interval respects the bounds; a mean ± 1.96 SE interval can run
  past them.
- **Small samples (20–46 units).** The bootstrap needs no normality
  assumption. The t-interval is kept as a **sensitivity check**; if both
  intervals agree, the conclusion doesn't hinge on the method.
- **Ratios and correlations.** q_micro = ΣC/ΣK and Spearman ρ have no simple
  standard-error formula. The bootstrap handles them the same way as a mean.
- **The paired design.** The same pools appear under several conditions (and
  under both attackers). A **paired bootstrap** resamples a pool ID once and
  carries both conditions' scores together, then computes the difference.
  Shared pool difficulty cancels, which is the whole point of pairing.
  Resampling each condition separately and subtracting would throw that away.
- **Clustering across cells.** A correlation pooled over the 9 grid cells has
  every pool appearing up to 9 times. Resampling pool IDs, and carrying all of
  a pool's rows, keeps the pool as the unit (a cluster bootstrap).

## The exact settings (D13)
- 10,000 resamples, seed 42, with a fresh generator for each interval, so any
  single interval can be reproduced alone.
- 95% intervals generally; 90% for the frozen identifier near-baseline rule.
- Intervals are not adjusted for multiple comparisons; the plan specifies no
  adjustment. Treat any single borderline interval among many with care.

## One sentence for the paper
"Uncertainty is quantified with percentile-bootstrap confidence intervals
(10,000 resamples) over the independent experimental units (pools for game J,
documents for game O); paired comparisons resample units jointly across
conditions, and t-intervals are reported as a sensitivity check."

## What the bootstrap cannot do
It estimates sampling variability for *these* pools and documents drawn from
*this* corpus. It does not make the result generalize to other corpora,
models or attackers, and it does not turn a non-significant difference into
equivalence (results plan §20).
