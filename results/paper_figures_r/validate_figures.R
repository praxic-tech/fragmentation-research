# validate_figures.R
# Checks every figure CSV against the frozen source artifacts, independently of
# the plotting scripts: values, CIs, sample sizes, attacker names and post-hoc
# flags. Also checks that every output file exists. Stops with an error if any
# check fails.
#
# Run from the repository root:
#   Rscript results/paper_figures_r/validate_figures.R

dir <- "results/paper_figures_r"
tab <- function(f) read.csv(file.path("results/final_analysis/TABLES", f))
fig <- function(f) read.csv(file.path(dir, paste0(f, ".csv")))

failures <- 0
check <- function(label, ok) {
  ok <- isTRUE(ok)
  if (!ok) failures <<- failures + 1
  cat(sprintf("  %s  %s\n", if (ok) "ok  " else "FAIL", label))
}
same <- function(a, b) isTRUE(all.equal(as.numeric(a), as.numeric(b), tolerance = 1e-12))

# ---- Figure 1 -------------------------------------------------------------------
cat("fig1_headline_attackers\n")
f <- fig("fig1_headline_attackers"); B <- tab("table_B_headline_J.csv")
for (a in c("Memon-inspired", "Embedding (post-hoc exploratory)", "One-shot Sonnet")) {
  src <- B[B$attacker == a, ]
  for (m in c("F1_L", "F1_J")) {
    row <- f[f$layer == "estimate" & f$attacker == a & f$metric == m, ]
    check(paste(a, m, "mean and 95% CI"),
          same(c(row$value, row$lo, row$hi),
               unlist(src[, paste0(m, c("_mean", "_lo", "_hi"))])))
  }
}
an <- B[B$attacker == "Analytic one-bucket", ]
check("baseline lines = analytic F1_L / F1_J means",
      same(f$value[f$layer == "baseline"], c(an$F1_L_mean, an$F1_J_mean)))
check("46 pools on every row", all(f$n_pools == 46))
check("post-hoc flag only on the embedding rows",
      identical(f$post_hoc, f$attacker == "Embedding (post-hoc exploratory)"))

# ---- Figures 2 and 3 ------------------------------------------------------------------
C <- tab("table_C_grid_J.csv"); CS <- C[C$attacker == "One-shot Sonnet", ]
cat("fig2_grid_reconstruction\n")
f <- fig("fig2_grid_reconstruction")
check("9 cells", nrow(f) == 9 && setequal(f$condition, CS$condition))
s <- CS[match(f$condition, CS$condition), ]
check("F1_J means and 95% CIs", same(c(f$F1_J, f$lo, f$hi), c(s$F1_J_mean, s$F1_J_lo, s$F1_J_hi)))
check("baseline ticks = b_J", same(f$b_J, s$b_J_mean))
check("pools: 24 per cell, 23 for random / token-window",
      all(f$pools_completed == ifelse(f$condition == "random / token-window", 23, 24)))

cat("fig3_linkage_vs_ordering\n")
f <- fig("fig3_linkage_vs_ordering")
CA <- C[C$attacker == "Analytic one-bucket", ]
L <- f[f$metric == "F1_L", ]; Q <- f[f$metric == "q", ]
sl <- CS[match(L$condition, CS$condition), ]; sq <- CS[match(Q$condition, CS$condition), ]
check("F1_L means and 95% CIs", same(c(L$value, L$lo, L$hi), c(sl$F1_L_mean, sl$F1_L_lo, sl$F1_L_hi)))
check("q_micro and 95% CIs", same(c(Q$value, Q$lo, Q$hi), c(sq$q_micro, sq$q_micro_lo, sq$q_micro_hi)))
check("F1_L reference = analytic linkage baseline",
      same(L$reference, CA$F1_L_mean[match(L$condition, CA$condition)]))
check("q reference = 0.5 (chance)", all(Q$reference == 0.5))

# ---- Figure 4 -------------------------------------------------------------------------
cat("fig4_identifiers\n")
f <- fig("fig4_identifiers"); E <- tab("table_E_identifier_J.csv"); E3 <- tab("table_E3_identifier_membership.csv")
src_name <- c("Random partition" = "Random", "Memon-inspired" = "Memon-inspired",
              "Embedding (post-hoc exploratory)" = "Embedding (post-hoc exploratory)",
              "One-shot Sonnet" = "One-shot Sonnet")
for (r in names(src_name)) {
  a <- f[f$panel == "a" & f$layer == "estimate" & f$row == r, ]
  b <- f[f$panel == "b" & f$layer == "estimate" & f$row == r, ]
  e <- E[E$attacker == src_name[r], ]; e3 <- E3[E3$attacker == src_name[r], ]
  check(paste(r, "F1_J mean and 95% CI"), same(c(a$value, a$lo, a$hi), c(e$F1_J_mean, e$F1_J_lo, e$F1_J_hi)))
  check(paste(r, "linkage precision and 95% CI"),
        same(c(b$value, b$lo, b$hi), c(e3$linkage_precision_mean, e3$lo, e3$hi)))
}
ref <- f[f$layer == "reference", ]
check("references: analytic 0.10, schema-order 0.20, chance 1/7",
      same(ref$value, c(0.1, 0.2, 1 / 7)))
check("20 pools", all(f$n_pools == 20))
check("panel (b) and the embedding row flagged post hoc",
      all(f$post_hoc[f$panel == "b"]) && all(f$post_hoc[f$row == "Embedding (post-hoc exploratory)"]) &&
      !any(f$post_hoc[f$panel == "a" & f$row != "Embedding (post-hoc exploratory)"]))

# ---- Figure 5 and Appendix C -------------------------------------------------------------
P <- read.csv("results/single_token_edge/analysis/per_pool.csv"); P <- P[P$attacker == "One-shot Sonnet", ]
S <- jsonlite::fromJSON("results/single_token_edge/analysis/summary.json")$attackers[["One-shot Sonnet"]]
cat("fig5_single_token\n")
f <- fig("fig5_single_token")
pr <- f[f$layer == "pool", ]
src <- P[match(paste(pr$pool, pr$arm), paste(P$pool, P$condition)), ]
check("40 per-pool A_VJ values (20 pools x 2 arms)", nrow(pr) == 40 && same(pr$value, src$A_VJ))
am <- f[f$layer == "arm_mean", ]
check("arm means = frozen summary means", same(am$value, c(S$means$sentence$A_VJ, S$means$token$A_VJ)))
check("arm means = mean of the 20 pools",
      same(am$value, c(mean(P$A_VJ[P$condition == "sentence"]), mean(P$A_VJ[P$condition == "token"]))))
pd <- f[f$layer == "pool_difference", ]
check("20 pool differences, all positive", nrow(pd) == 20 && all(pd$value > 0))
md <- f[f$layer == "mean_difference", ]
pa <- S$paired_sentence_minus_token$A_VJ
check("mean difference and 95% CI = frozen paired bootstrap",
      same(c(md$value, md$lo, md$hi), c(pa$mean_diff, pa$ci95)))
check("mean difference = mean of the pool differences", same(md$value, mean(pd$value)))
check("sign test inputs: 20 of 20 positive", pa$n_positive == 20 && pa$n_effective == 20)
check("every row flagged post hoc", all(f$post_hoc))

cat("figC_token_raw_vs_null\n")
f <- fig("figC_token_raw_vs_null")
po <- f[f$layer == "pool" & f$series == "observed", ]; pn <- f[f$layer == "pool" & f$series == "null", ]
so <- P[match(paste(po$pool, po$arm), paste(P$pool, P$condition)), ]
sn <- P[match(paste(pn$pool, pn$arm), paste(P$pool, P$condition)), ]
check("observed V_J per pool", nrow(po) == 40 && same(po$value, so$V_J))
check("oracle-size null V_J per pool", nrow(pn) == 40 && same(pn$value, sn$null_oracle_V_J))
m <- f[f$layer == "arm_mean", ]
expect <- c(observed.sentence = mean(P$V_J[P$condition == "sentence"]),
            observed.token    = mean(P$V_J[P$condition == "token"]),
            null.sentence     = mean(P$null_oracle_V_J[P$condition == "sentence"]),
            null.token        = mean(P$null_oracle_V_J[P$condition == "token"]))
check("arm means (0.762 / 0.155 observed; 0.423 / 0.141 null)",
      same(m$value, expect[paste(m$series, m$arm, sep = ".")]))
check("every row flagged post hoc", all(f$post_hoc))

# ---- Appendix A -----------------------------------------------------------------------------
cat("figA_gameO_vs_gameJ\n")
f <- fig("figA_gameO_vs_gameJ"); D <- tab("table_D_game_O.csv"); DS <- D[D$attacker == "One-shot Sonnet", ]
o <- f[f$game == "O", ]; d <- DS[match(o$condition, DS$condition), ]
check("Game O = (1 + tau)/2 of the frozen tau and CI",
      same(c(o$value, o$lo, o$hi), (1 + c(d$tau_mean, d$tau_lo, d$tau_hi)) / 2))
check("Game O documents: 100 headline, 30 per cell",
      all(o$n_units == ifelse(o$condition == "headline (full length)", 100, 30)))
j <- f[f$game == "J", ]
hj <- B[B$attacker == "One-shot Sonnet", ]
jsrc <- rbind(data.frame(condition = "headline (full length)", hj[, c("F1_J_mean", "F1_J_lo", "F1_J_hi", "completed")]),
              CS[, c("condition", "F1_J_mean", "F1_J_lo", "F1_J_hi", "completed")])
js <- jsrc[match(j$condition, jsrc$condition), ]
check("Game J F1_J and 95% CI", same(c(j$value, j$lo, j$hi), c(js$F1_J_mean, js$F1_J_lo, js$F1_J_hi)))
check("Game J pools: 46 headline, 24 / 23 per cell", same(j$n_units, js$completed))

# ---- Appendix B -----------------------------------------------------------------------------
cat("figB_resource_scaling\n")
f <- fig("figB_resource_scaling")
M <- read.csv("results/final_analysis/MASTER_RESULTS.csv")
MS <- M[M$attacker == "One-shot Sonnet" & M$game == "J", ]
pre <- f[!f$post_hoc, ]
ms <- MS[match(paste(pre$cell, pre$unit), paste(MS$cell, MS$unit_id)), ]
check("282 prespecified units, tokens = answer_call_output_tokens",
      nrow(pre) == 282 && same(pre$output_tokens, ms$answer_call_output_tokens) &&
      same(pre$n_fragments, ms$n_fragments))
rb <- pre[pre$rbnc %in% c(TRUE, "TRUE"), ]
check("exactly one non-completion: 322 fragments at 128,000 tokens",
      nrow(rb) == 1 && rb$n_fragments == 322 && rb$output_tokens == 128000)
tk <- f[f$post_hoc, ]
check("20 single-token units", nrow(tk) == 20)
check("8 answered by the repair call, 12 by the first call",
      sum(grepl("-r1$", tk$answering_call)) == 8)
check("the 3 units whose repair call hit 128k use their first call",
      all(!grepl("-r1$", tk$answering_call[tk$unit %in% c("pool_022", "pool_029", "pool_052")])))
check("token-arm fragment counts = frozen per-pool counts",
      same(tk$n_fragments, P$n_fragments[P$condition == "token"][match(tk$unit, P$pool[P$condition == "token"])]))

# ---- Figure 6: the granularity gradient ----------------------------------------------------
# Checked against the frozen sources, not against fig6's own script: the D16
# analysis for the two anchor arms, the D18 visible analysis for the three new
# ones, and the recovery JSON for panel (b).
cat("fig6_granularity_gradient\n")
suppressPackageStartupMessages(library(jsonlite))
f6  <- fig("fig6_granularity_gradient")
s16 <- fromJSON("results/single_token_edge/analysis/summary.json")$attackers[["One-shot Sonnet"]]$means
s18 <- fromJSON("results/gradient/visible_analysis/summary.json")
rc  <- fromJSON("results/gradient/recovery.json")

check("5 arms, ordered fine to coarse",
      nrow(f6) == 5 && identical(f6$arm, c("1-word", "2-word", "3-word", "4-word", "sentence")))
check("anchor arms' A_VJ / V_J / V_L = the frozen D16 analysis",
      same(c(f6$A_VJ[f6$arm == "sentence"], f6$V_J[f6$arm == "sentence"], f6$V_L[f6$arm == "sentence"],
             f6$A_VJ[f6$arm == "1-word"],  f6$V_J[f6$arm == "1-word"],  f6$V_L[f6$arm == "1-word"]),
           c(s16$sentence$A_VJ, s16$sentence$V_J, s16$sentence$V_L,
             s16$token$A_VJ,    s16$token$V_J,    s16$token$V_L)))
for (a in c("4-word", "3-word", "2-word")) {
  k <- c("4-word" = "w4", "3-word" = "w3", "2-word" = "w2")[[a]]
  check(paste(a, "A_VJ / V_J / V_L = the D18 visible analysis"),
        same(c(f6$A_VJ[f6$arm == a], f6$V_J[f6$arm == a], f6$V_L[f6$arm == a]),
             c(s18$arms[[k]]$A_VJ, s18$arms[[k]]$V_J, s18$arms[[k]]$V_L)))
}
check("the D18 nulls used the frozen 10,000 permutations",
      s18$permutations_per_pool_condition_null == 10000)
check("the D18 nulls kept the frozen namespace",
      grepl("single-token-edge-v1", s18$null_namespace))
check("20 pools scored in every new arm",
      all(vapply(c("w4", "w3", "w2"), function(k) s18$arms[[k]]$n_pools == 20, logical(1))))
check("panel (b) recovered / floor percentages = recovery.json",
      same(c(f6$recovered, f6$floor),
           c(vapply(f6$arm, function(a) rc[[a]]$recovered_pct, numeric(1)),
             vapply(f6$arm, function(a) rc[[a]]$floor_pct, numeric(1)))))
check("recovered is never below the floor it is measured against",
      all(f6$recovered >= f6$floor))
check("V_J <= V_L in every arm", all(f6$V_J <= f6$V_L + 1e-12))
check("the primary series is monotone in fragment length",
      !is.unsorted(f6$A_VJ) && !is.unsorted(f6$frag_words))
check("mean fragment lengths match the built cells (19.01 / 3.92 / 2.96 / 1.99 / 1.00)",
      same(round(f6$frag_words, 2), c(1.00, 1.99, 2.96, 3.92, 19.01)))

# ---- Files --------------------------------------------------------------------------------
cat("files\n")
for (n in c("fig1_headline_attackers", "fig2_grid_reconstruction", "fig3_linkage_vs_ordering",
            "fig4_identifiers", "fig5_single_token", "fig6_granularity_gradient",
            "figA_gameO_vs_gameJ", "figB_resource_scaling", "figC_token_raw_vs_null")) {
  check(paste(n, ": pdf svg png csv R"),
        all(file.exists(file.path(dir, paste0(n, c(".pdf", ".svg", ".png", ".csv", ".R"))))))
}

cat(sprintf("\n%d failure(s)\n", failures))
if (failures > 0) stop("figure validation failed")
