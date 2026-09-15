# fig5_single_token.R
# Figure 5 (main text): POST-HOC EXPLORATORY single-token boundary experiment
# (RUN_DECISIONS D16). Same 20 headline pools, same four-sentence excerpts,
# cut into sentences or into single whitespace tokens; one-shot Sonnet.
#
# Run from the repository root:
#   Rscript results/paper_figures_r/fig5_single_token.R

source("results/paper_figures_r/theme_paper.R")

# ---- Data -------------------------------------------------------------------
# Per-pool A_VJ from the frozen D16 analysis, and its frozen paired summary.
# The frozen analysis has a CI for the paired difference only, so the arm
# means in panel (a) are drawn without CIs (none is computed here).
pools   <- read.csv("results/single_token_edge/analysis/per_pool.csv")
summary <- jsonlite::fromJSON("results/single_token_edge/analysis/summary.json")
sonnet  <- summary$attackers[["One-shot Sonnet"]]
paired  <- sonnet$paired_sentence_minus_token$A_VJ

pools <- pools[pools$attacker == "One-shot Sonnet", ]
wide  <- merge(pools[pools$condition == "sentence", c("pool", "A_VJ")],
               pools[pools$condition == "token",    c("pool", "A_VJ")],
               by = "pool", suffixes = c("_sentence", "_token"))

plot_data <- rbind(
  data.frame(layer = "pool", pool = pools$pool, arm = pools$condition,
             value = pools$A_VJ, lo = NA, hi = NA),
  data.frame(layer = "arm_mean", pool = NA, arm = c("sentence", "token"),
             value = c(sonnet$means$sentence$A_VJ, sonnet$means$token$A_VJ), lo = NA, hi = NA),
  data.frame(layer = "pool_difference", pool = wide$pool, arm = "sentence - token",
             value = wide$A_VJ_sentence - wide$A_VJ_token, lo = NA, hi = NA),
  data.frame(layer = "mean_difference", pool = NA, arm = "sentence - token",
             value = paired$mean_diff, lo = paired$ci95[1], hi = paired$ci95[2])
)
plot_data$post_hoc <- TRUE

# ---- Plot -------------------------------------------------------------------
y_limits <- c(-0.2, 1)   # A_VJ is at most 1; it can fall below 0 (worse than the null)
arm_names <- c(sentence = "Sentence", token = "Single\ntoken")

# (a) Paired slope chart: one light line per pool, arm means as open markers.
pool_rows <- subset(plot_data, layer == "pool")
mean_rows <- subset(plot_data, layer == "arm_mean")

panel_a <- ggplot(pool_rows, aes(x = arm, y = value)) +
  geom_hline(yintercept = 0, linetype = "dashed", linewidth = ref_linewidth, colour = baseline_grey) +
  geom_line(aes(group = pool), colour = "grey75", linewidth = 0.3) +
  geom_point(colour = "grey60", size = 0.6) +
  geom_line(data = mean_rows, aes(group = 1), colour = sonnet_colour, linewidth = 0.6) +
  geom_point(data = mean_rows, shape = 21, fill = "white", colour = sonnet_colour,
             size = point_size + 0.4, stroke = point_stroke + 0.2) +
  scale_x_discrete(labels = arm_names, expand = expansion(add = 0.35)) +
  scale_y_continuous(limits = y_limits, breaks = seq(0, 1, 0.25), labels = axis_01_labels) +
  labs(x = NULL, y = expression(atop("Null-adjusted joint", "reconstruction " * (italic(A)[VJ])))) +
  theme_paper()

# (b) Estimation plot: the 20 per-pool differences and the frozen mean with
# its 95% paired-bootstrap CI, on the same vertical scale as (a).
diff_rows <- subset(plot_data, layer == "pool_difference")
mean_diff <- subset(plot_data, layer == "mean_difference")

panel_b <- ggplot() +
  geom_hline(yintercept = 0, linetype = "dashed", linewidth = ref_linewidth, colour = baseline_grey) +
  geom_point(data = diff_rows, aes(x = 1, y = value), colour = "grey55", size = 0.7,
             position = position_jitter(width = 0.12, height = 0, seed = 1)) +
  # End caps, because the CI is only slightly taller than the marker.
  geom_errorbar(data = mean_diff, aes(x = 1.65, ymin = lo, ymax = hi), width = 0.16,
                colour = sonnet_colour, linewidth = ci_linewidth) +
  geom_point(data = mean_diff, aes(x = 1.65, y = value), shape = 21, fill = "white",
             colour = sonnet_colour, size = point_size + 0.4, stroke = point_stroke + 0.2) +
  scale_x_continuous(limits = c(0.6, 2.05), breaks = c(1, 1.65), labels = c("Pools", "Mean")) +
  scale_y_continuous(limits = y_limits, breaks = seq(0, 1, 0.25), labels = axis_01_labels) +
  labs(x = NULL, y = expression(atop("Paired difference", "(sentence " - " token)"))) +
  theme_paper()

fig <- (panel_a | panel_b) + plot_annotation(tag_levels = list(c("(a)", "(b)")))

# ---- Export -----------------------------------------------------------------
save_figure(fig, "fig5_single_token", width = col_width, height = 2.1, data = plot_data)
