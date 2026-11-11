\# Final Analysis and Reporting Plan



\## Purpose



At the end of the approved experimental run, I want a complete research-analysis package, not only aggregate scores.



The final package must let us answer:



1\. How reconstructable are fragmented prose documents?

2\. How does reconstructability change with fragmentation strategy and granularity?

3\. How do document length, fragment count, and fragment size relate to reconstructability?

4\. Does fragmentation protect identifier-style structured data from joint reconstruction?

5\. Which part of reconstruction remains possible: linkage, ordering, or both?

6\. How do the tested adversaries differ?

7\. Where do resource limits cause attacker non-completion?

8\. What conclusions are actually supported by the evidence?



Do not add new paid attacks or experiments merely to make tables symmetrical.



Use every \*\*prespecified applicable attacker and baseline\*\* on the data for which it was approved.



There is NO new standalone Game L experiment. Whenever linkage F1 is reported for Game J, it is the linkage component extracted from the J reconstruction.



\---



\# 1. Preserve the complete raw result set



Create a machine-readable master dataset containing one row per independent experimental unit / attacker / condition.



Preserve at minimum:



\- corpus

\- game

\- attacker

\- fragmentation strategy

\- granularity

\- pool ID or document ID

\- screening / primary / headline / hierarchical-rescue / hierarchical-filler designation

\- original document word count

\- original document character count if available

\- number of source documents in pool

\- total number of fragments

\- fragments per source document

\- mean fragment length

\- median fragment length

\- minimum and maximum fragment length

\- total prompt/input size if available

\- completion status

\- RBNC status

\- malformed/repair status

\- transport retry status

\- token usage

\- monetary cost

\- all raw scorer counts

\- all final metrics



Never retain only rounded aggregate tables.



Keep full-precision values in the analysis dataset.



Every paper figure/table must have a corresponding exported CSV containing exactly the data used to produce it.



\---



\# 2. Experimental-unit rules



Respect the actual independent sampling unit.



\## Game J



The independent unit is the \*\*pool\*\*, not an individual fragment pair.



Confidence intervals, bootstraps, comparisons, and uncertainty calculations for J must therefore resample pools.



Do NOT bootstrap individual fragment pairs.



\## Game O



The independent unit is the \*\*document\*\*.



Document-level analyses and uncertainty must operate at the document level.



\---



\# 3. Game J metrics



For every applicable J attacker and condition, report:



\### Primary reconstruction metrics



\- directed-pair precision

\- directed-pair recall

\- F1\_J



Raw F1\_J is the main reconstruction metric.



\### Baseline comparison



Report:



\- analytic J baseline b\_J

\- baseline-normalized advantage:



&#x20; A\_J = (F1\_J - b\_J) / (1 - b\_J)



Calculate the baseline per pool before aggregation where appropriate.



\### Linkage/order decomposition



Report:



\- linkage F1\_L

\- q = correctly directed co-clustered pairs / correctly co-clustered true pairs

\- F1\_L × q

\- verify numerically that:



&#x20; F1\_J = F1\_L × q



where the quantities are defined consistently.



For q:



\- do not average undefined q values

\- report the number/fraction of pools where K = 0

\- report the micro aggregate:



&#x20; q\_micro = sum(C) / sum(K)



\### Secondary J diagnostics



Report:



\- exact complete-record reconstruction rate

\- number of predicted clusters

\- predicted cluster-size distribution

\- true positive directed pairs

\- false positive directed pairs

\- false negative directed pairs

\- completion rate

\- RBNC rate

\- malformed/repair rate where relevant



Do NOT describe F1\_J as “percent of document text recovered.”



It is a directed pairwise reconstruction score.



\---



\# 4. Game O metrics



For every applicable O attacker and condition, report:



\### Primary



\- Kendall tau



\### Secondary



\- fraction of correctly ordered fragment pairs

\- exact complete-order reconstruction rate

\- mean absolute position displacement

\- median absolute position displacement

\- maximum position displacement if already supported

\- run/span diagnostics already implemented

\- fragment count

\- document length

\- completion/RBNC status



Game O remains the membership-oracle reference.



Do not describe it as an upper bound or mathematical ceiling on J.



\---



\# 5. Identifier corpus



The identifier analysis has a separate interpretation from prose.



\## Final identifier J sample



Use only the frozen 20-pool identifier-J primary sample.



Do not extend the sample in response to the result.



The earlier identifier O/L experiments remain exploratory and must not be silently merged into the final confirmatory estimates.



\## Identifier baselines



Report both:



\### Analytic baseline



F1\_J = 0.10



\### Schema-aware baseline



F1\_J = 0.20



The schema-aware baseline:



\- sees only attacker-visible prompt text

\- infers field type from formatting

\- knows the fixed schema order

\- receives no source-record membership

\- does not use hidden truth to construct its answer



\## Identifier primary analysis



For every approved applicable J attacker/baseline, report:



\- F1\_J

\- directed-pair precision

\- directed-pair recall

\- F1\_L

\- q

\- analytic-baseline advantage

\- schema-aware-baseline advantage

\- completion rate



The main identifier privacy interpretation should emphasize \*\*linkage\*\*.



q is partly driven by the obvious fixed field template and must be described primarily as a template/order diagnostic.



\## Frozen equivalence-style criterion



Calculate the mean advantage over the schema-aware baseline and its frozen 90% confidence interval.



The result qualifies as “near the schema-aware baseline” only if the ENTIRE 90% CI lies inside:



\[-0.10, +0.10]



A nonsignificant difference alone is NOT evidence of equivalence.



Do not change the ±0.10 margin after seeing the result.



\## Intended identifier claim



Any final wording must remain narrow.



Possible form, only if supported:



> On the tested identifier corpus, fragmentation substantially limited joint source-linkage and ordering reconstruction under the evaluated attackers.



Do NOT generalize this to:



\- all identifiers

\- all structured records

\- all fragmentation systems

\- all possible attackers



\---



\# 6. Prose headline J analysis



The headline condition is the full-length reference cut.



For every prespecified applicable adversary and baseline, report:



\- mean F1\_J

\- median F1\_J

\- confidence interval

\- F1\_L

\- q / q\_micro

\- A\_J

\- directed precision

\- directed recall

\- exact reconstruction

\- completion rate

\- RBNC rate

\- cost per completed pool

\- token usage if available



Also preserve and visualize the full pool-level distribution.



Do not report only means.



\## Attacker comparisons



Where two attackers both completed the same pools, perform paired pool-level comparisons.



Report:



\- paired mean difference

\- paired median difference

\- confidence interval on the paired difference



Do not compare attackers as if they had identical samples when completion differs.



Never choose the best attacker separately on each pool and then report the resulting per-pool maximum as an attacker score.



If reporting a “strongest tested attacker,” select it globally under an explicit rule.



\---



\# 7. Prose Grid J analysis



Primary Grid J uses pools 2–25.



Pool 1 remains screening/development and must remain separate from the primary grid estimates.



The retained cells are:



\- random × sentence

\- random × clause

\- random × token-window

\- semantic × sentence

\- semantic × clause

\- coherence-sever × clause

\- coherence-sever × token-window

\- subject-verb × sentence

\- subject-verb × clause



Semantic × sentence is the ordinary sentence-splitting reference condition.



\## For every grid cell report



\- F1\_J

\- directed precision

\- directed recall

\- analytic baseline

\- A\_J

\- F1\_L

\- q / q\_micro

\- exact reconstruction

\- fragment count

\- fragments per document

\- mean fragment length

\- median fragment length

\- completion / RBNC

\- cost where applicable



Use the same 24 paired pools whenever available.



\## Grid comparisons



Because the same source pools appear across conditions, exploit the paired design.



Report paired effect sizes and confidence intervals for meaningful comparisons.



Do NOT pretend the grid is a complete factorial design.



Some strategy × granularity combinations do not exist.



Make comparisons only where the design actually supports them.



Important comparison families include:



\### Within granularity



For example:



\- sentence-level strategies against other available sentence-level strategies

\- clause-level strategies against other clause-level strategies

\- token-window strategies where applicable



\### Within strategy



Compare granularity where that strategy has multiple retained granularities.



Examples:



\- random sentence vs clause vs token

\- semantic sentence vs clause

\- coherence clause vs token

\- subject-verb sentence vs clause



Do not manufacture a missing cell.



\---



\# 8. Relationship: granularity vs reconstructability



This is a major analysis question.



Ask:



> How does reconstruction resistance change as fragmentation becomes finer or coarser?



Analyze the relationship between granularity and:



\- F1\_J

\- F1\_L

\- q

\- A\_J

\- Game O Kendall tau



Show both:



1\. raw cell-level results

2\. paired differences where the same pools/documents appear under multiple granularities



Interpret carefully because granularity also changes fragment count and fragment size.



Do not automatically conclude that a boundary rule itself caused the effect.



\---



\# 9. Relationship: fragmentation strategy vs reconstructability



Ask:



> Holding the available granularity approximately comparable, how much does boundary-selection strategy change reconstruction?



Compare:



\- random

\- semantic

\- coherence-sever

\- subject-verb



where the grid actually contains comparable cells.



Analyze separately:



\- overall J reconstruction

\- linkage component F1\_L

\- ordering component q

\- Game O ordering



This should let us identify whether a strategy mainly damages:



\- source linkage

\- ordering

\- both



\---



\# 10. Relationship: document length vs reconstructability



This is a required paper analysis.



\## Game O



At the document level, examine:



\- original document word count vs Kendall tau

\- original document word count vs correctly ordered-pair fraction

\- original document word count vs exact ordering

\- original document word count vs absolute displacement



\## Game J



Because J is scored at pool level, construct pool-level length covariates such as:



\- mean source-document word count

\- median source-document word count

\- minimum/maximum document length if useful

\- total words represented by the pool



Examine relationships with:



\- F1\_J

\- F1\_L

\- q

\- A\_J

\- completion/RBNC



Use scatterplots plus a simple monotonic association statistic such as Spearman rho with an appropriate pool-level confidence interval.



If a simple regression is reported, label it exploratory and report effect size + uncertainty.



Do not imply causality.



\---



\# 11. Relationship: fragment count vs reconstructability



This is required.



Ask:



> Does increasing the number of fragments make reconstruction harder?



For J examine pool-level:



\- total fragments vs F1\_J

\- fragments per source document vs F1\_J

\- total fragments vs F1\_L

\- total fragments vs q

\- total fragments vs A\_J

\- total fragments vs RBNC probability/resource consumption



For O examine document-level:



\- fragment count vs Kendall tau

\- fragment count vs exact reconstruction

\- fragment count vs correctly ordered pairs



This relationship is especially important because some fragmentation strategies create substantially more fragments than others.



Do NOT interpret this as proving that fragment count alone causes resistance.



\---



\# 12. Relationship: fragment size vs reconstructability



Analyze:



\- mean fragment word count

\- median fragment word count

\- fragment-length variance if useful



against:



\- F1\_J

\- F1\_L

\- q

\- A\_J

\- O Kendall tau



Question:



> Are smaller fragments systematically harder to reconstruct?



Again, report association rather than causal claims.



\---



\# 13. Fragmentation intensity / mechanics



Create a mechanics summary for every grid cell.



At minimum report:



\- source-document length

\- fragments per document

\- mean fragment length

\- median fragment length

\- fragment-length standard deviation

\- minimum/maximum fragment length

\- total fragments per pool



If useful, derive a descriptive fragmentation-intensity quantity such as:



fragments per 1,000 source words



This may help distinguish:



\- effects associated with boundary strategy

\- effects associated with simply generating more/smaller fragments



Do not claim a causal decomposition unless the experimental design actually supports it.



\---



\# 14. Linkage-vs-ordering decomposition



This should be a major explanatory analysis.



For each strategy / attacker, examine the position in:



(F1\_L, q)



space.



Interpretation:



\- low F1\_L, high q:

&#x20; fragmentation mainly disrupts source linkage

\- high F1\_L, low q:

&#x20; membership remains recoverable but order becomes difficult

\- low F1\_L, low q:

&#x20; both are damaged

\- high F1\_L, high q:

&#x20; reconstruction remains easy



This decomposition should be used to explain WHY F1\_J changes.



Do not rely only on the scalar F1\_J ranking.



\---



\# 15. Headline-vs-grid comparison



Compare the full-length headline reference condition to its corresponding grid/development reference condition.



This is primarily a generalization/check analysis.



Ask:



\- did performance materially change at full document length?

\- did fragment count increase?

\- did resource consumption increase?

\- did RBNCs become more common?

\- was reconstruction easier/harder for longer real documents?



Do not merge headline and grid pools into one estimate.



\---



\# 16. Hierarchical attacker analysis



Hierarchical is a decomposed/scalable attacker, not automatically a stronger attacker.



Keep two analyses separate.



\## A. RBNC rescue



For every headline pool where one-shot exhausted the 128k budget:



report:



\- one-shot status = RBNC

\- hierarchical completion

\- hierarchical F1\_J

\- F1\_L

\- q

\- cost

\- fragment count



This answers:



> Can decomposition complete attacks on pools that the monolithic attacker cannot finish?



\## B. Random filler paired comparison



On the prespecified random filler pools where both attackers complete:



compare:



\- one-shot F1\_J vs hierarchical F1\_J

\- F1\_L

\- q

\- cost

\- completion

\- token usage



Use paired differences.



Do not mix the failure-enriched rescue subset with random fillers and call the resulting 12-pool average representative of headline performance.



\## Hierarchical diagnostics



Report:



\- k

\- number of candidate edges

\- same-record candidate recall

\- adjacent-pair recall

\- record connectivity

\- pair-judgment statistics if available

\- cluster output statistics

\- bridge-round use

\- completion

\- cost



Also preserve the frozen oracle-ceiling diagnostic:



\- oracle F1\_L

\- oracle q

\- oracle F1\_J



Clearly label it:



\*\*DIAGNOSTIC CEILING — NOT AN ATTACKER RESULT\*\*



The oracle only establishes that the candidate graph/downstream architecture does not impose a low ceiling.



Do not claim that all remaining error is solely caused by Sonnet.



\---



\# 17. Non-completion / RBNC analysis



Resource-bounded non-completion is itself important.



Report by:



\- corpus

\- attacker

\- strategy

\- granularity

\- fragment count

\- document length



For one-shot, examine whether RBNC correlates with:



\- fragment count

\- total prompt size

\- total source-document length

\- particular fragmentation cells



RBNC is not F1 = 0.



Do not silently remove it.



Numerical paired comparisons use pools where both attackers completed, while completion rate is reported separately.



\---



\# 18. Resource/cost analysis



Create a resource table containing:



\- requests submitted

\- requests completed

\- provider refusals

\- transport retries

\- repairs

\- RBNCs

\- input tokens

\- output/reasoning tokens

\- dollars/credit

\- cost per completed pool

\- cost per condition

\- total experimental cost



Where useful analyze:



\- fragment count vs output tokens

\- prompt size vs output tokens

\- fragment count vs cost

\- fragment count vs probability of RBNC



This is especially relevant to the comparison between one-shot and hierarchical attack architectures.



\---



\# 19. Error analysis



Produce a qualitative error taxonomy after quantitative scoring.



Possible categories include:



\- correct membership but wrong ordering

\- wrong membership with mostly correct local order

\- merged source documents

\- split source document

\- local adjacent swap

\- large-span displacement

\- plausible semantic but incorrect grouping

\- singleton/isolated fragments

\- near-perfect reconstruction

\- catastrophic reconstruction failure



Selection of examples must be transparent.



Do not select only examples that make fragmentation look successful.



Clearly state whether examples were selected:



\- randomly

\- by quantile

\- by predefined rule



Qualitative examples are illustrative, not inferential.



\---



\# 20. Statistical reporting principles



Prefer effect sizes and uncertainty over binary significance language.



Report:



\- means where appropriate

\- medians

\- distributions

\- confidence intervals

\- paired differences for paired designs



Do not interpret:



“not statistically significant”



as:



“equivalent.”



The identifier ±0.10 rule is the only currently frozen explicit equivalence-style criterion.



Do not invent new equivalence margins after seeing results.



\---



\# 21. Required paper figures



Generate publication-ready versions of at least the following.



Every figure must also export its exact underlying source table.



\## Figure 1 — Headline J attacker comparison



Show F1\_J by applicable attacker/baseline with uncertainty.



Include completion information where necessary.



\## Figure 2 — Grid J strategy/granularity



Show all 9 retained cells.



A heatmap, point-range plot, or similarly readable layout is acceptable.



Show F1\_J and uncertainty.



\## Figure 3 — Linkage vs ordering decomposition



Plot:



x = F1\_L

y = q



Label/color by fragmentation condition or attacker.



Purpose:



show whether resistance comes from linkage failure, ordering failure, or both.



\## Figure 4 — Grid O



Show Kendall tau across fragmentation cells with uncertainty.



\## Figure 5 — Identifier J



Show:



\- analytic baseline 0.10

\- schema-aware baseline 0.20

\- all applicable approved identifier attackers

\- confidence interval



Also visually indicate the schema-baseline comparison.



\## Figure 6 — Document length vs reconstructability



Scatter / relationship plot for:



document or pool length vs reconstruction score.



Produce appropriate O and J variants if needed.



\## Figure 7 — Fragment count vs reconstructability



Show fragment count against F1\_J.



Also produce O tau vs fragment count if informative.



\## Figure 8 — Fragment size vs reconstructability



Mean/median fragment length against reconstruction.



\## Figure 9 — Completion / RBNC



Show completion rates by attacker / condition if RBNCs are numerous enough to matter.



\## Figure 10 — Resource scaling



If informative, show:



fragment count or prompt size vs token usage/cost.



Do not create decorative figures that add no analytical value.



\---



\# 22. Required paper tables



Produce at minimum:



\## Table A — Corpus/design summary



For each experimental family:



\- corpus

\- game

\- sample size

\- pool size

\- fragmentation condition

\- attackers

\- primary metric



\## Table B — Headline J



All applicable attackers/baselines and:



\- F1\_J

\- F1\_L

\- q

\- A\_J

\- completion

\- CI



\## Table C — Grid J



All nine cells and primary decomposition metrics.



\## Table D — Game O



Grid/headline O results.



\## Table E — Identifier J



Include:



\- analytic baseline

\- schema-aware baseline

\- attacker results

\- schema advantage

\- 90% CI

\- frozen ±0.10 decision



\## Table F — Hierarchical



Separate:



\- RBNC rescue

\- paired random fillers

\- oracle diagnostic



\## Table G — Resource/completion



Tokens, cost, completion, RBNCs, repairs and retries.



\---



\# 23. Adversary naming



Use exact, defensible names.



Do not call the Jaccard-Greedy or Jaccard-MST attackers faithful implementations of Memon.



Use names such as:



\- Random

\- Jaccard-Greedy

\- Jaccard-MST

\- Memon-inspired

\- One-shot Sonnet

\- Hierarchical/decomposed Sonnet



unless the implementation genuinely changes.



If a faithful Memon/PPM implementation is later available, label it separately.



\---



\# 24. Screening vs primary results



Preserve the exploratory/confirmatory distinction.



Pool 1 was used for screening/development.



Do not merge pool 1 into the primary 24-pool grid estimates.



It can appear in:



\- methodology history

\- screening appendix

\- exploratory discussion



but not as if it were part of the untouched primary grid sample.



\---



\# 25. Claim-to-evidence matrix



At the very end, produce a table with:



\- proposed claim

\- experiment supporting it

\- metric

\- numerical result

\- uncertainty

\- supported / partially supported / unsupported

\- strongest defensible wording



Include at least these candidate questions:



\### Data-type claim



Does fragmentation substantially resist reconstruction for identifier-style structured records?



\### General prose claim



Does fragmented prose retain meaningful reconstruction signal?



\### Strategy claim



Does fragmentation strategy materially affect reconstructability?



\### Granularity claim



Does finer/coarser fragmentation relate to reconstruction resistance?



\### Length claim



Does document length relate to reconstruction success?



\### Fragment-count claim



Does increasing fragment count relate to reconstruction success?



\### Mechanism claim



Is resistance primarily due to linkage failure, ordering failure, or both?



\### Attacker claim



Which tested attacker performs strongest under the tested conditions?



\### Resource claim



Does hierarchical decomposition reduce the whole-pool resource-completion problem?



Do NOT force every claim to be supported.



If the evidence contradicts an intended claim, say so.



\---



\# 26. Reproducibility package



Preserve:



\- analysis scripts

\- scorer version

\- seeds

\- exact pool lists

\- raw API answers

\- parsed answers

\- raw metrics

\- aggregate metrics

\- figure source CSVs

\- final figures

\- table source CSVs

\- model identifiers

\- request parameters

\- completion/error logs

\- cost ledger

\- commit hashes



Every number in the paper should be traceable back to a raw experimental unit.



\---



\# 27. Figure output formats



For every final paper figure export:



\- PDF or SVG vector version

\- PNG preview

\- source CSV

\- script that generated it



Use consistent paper typography, labels and metric ranges.



Do not manually edit plotted values after generation.



\---



\# 28. Analysis labeling



Separate every analysis into one of:



\- primary / prespecified

\- secondary / prespecified

\- diagnostic

\- exploratory / post hoc



Especially label the following correctly:



\### Primary / central



\- raw headline F1\_J

\- primary Grid J results

\- identifier frozen J analysis

\- O where prespecified



\### Diagnostic



\- q decomposition

\- hierarchical oracle ceiling

\- masking checks

\- resource mechanics



\### Exploratory unless explicitly frozen earlier



\- correlations discovered after scoring

\- unusual subgroup patterns

\- additional regressions

\- qualitative error patterns



Exploratory does NOT mean invalid.



It means we do not pretend it was hypothesized after seeing the data.



\---



\# 29. Do not add a standalone Game L run



This analysis plan does NOT authorize another paid Game L experiment.



For Game J:



F1\_L is computed from the membership portion of the joint reconstruction output.



Refer to it as:



> the linkage component of Game J



when appropriate.



Do not imply there was an independent confirmatory L experiment where none exists.



\---



\# 30. Final deliverable



At the end of the run I want one analysis directory containing:



\- `MASTER\_RESULTS.csv`

\- `HEADLINE\_J.csv`

\- `GRID\_J.csv`

\- `IDENTIFIER\_J.csv`

\- `GAME\_O.csv`

\- `HIERARCHICAL.csv`

\- `RESOURCE\_USAGE.csv`

\- `CLAIM\_EVIDENCE.md`

\- `RESULTS\_SUMMARY.md`

\- `FIGURES/`

\- `TABLES/`

\- `figure\_data/`

\- all analysis scripts



`RESULTS\_SUMMARY.md` should explain the results in plain English as well as technically.



It must answer:



1\. What was easiest to reconstruct?

2\. What was hardest?

3\. Which fragmentation strategy performed best and worst?

4\. Did granularity matter?

5\. Did document length matter?

6\. Did fragment count matter?

7\. Did fragment size matter?

8\. Was resistance caused more by linkage failure or ordering failure?

9\. Did identifiers behave differently from prose?

10\. Which attacker was strongest?

11\. Where did attackers fail due to resource limits?

12\. What can we actually claim?

13\. What can we NOT claim?

14\. What results were surprising?

15\. What should go in the main paper versus the appendix?



Do not tune analyses, exclusions, plots, or wording to favor the fragmentation defense.



The goal is to characterize what the experiment actually found.

