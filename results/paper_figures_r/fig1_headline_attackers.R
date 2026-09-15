# fig1_headline_attackers.R
# Figure 1 (main text): headline prose, Game J, attacker comparison on the
# 46 headline pools. Prespecified, except the embedding row (post hoc).
#
# Run from the repository root:
#   Rscript results/paper_figures_r/fig1_headline_attackers.R

source("results/paper_figures_r/theme_paper.R")

# ---- Data -------------------------------------------------------------------
# Frozen summary: pool means with 95% percentile-bootstrap CIs over the 46
# pools (RUN_DECISIONS D13). Nothing is recomputed here.
headline <- read.csv("results/final_analysis/TABLES/table_B_headline_J.csv")

attackers <- c("Memon-inspired", "Embedding (post-hoc exploratory)", "One-shot Sonnet")
est <- headline[headline$attacker %in% attackers, ]
bas <- headline[headline$attacker == "Analytic one-bucket", ]

plot_data <- rbind(
  data.frame(layer = "estimate", attacker = est$attacker, metric = "F1_L",
             value = est$F1_L_mean, lo = est$F1_L_lo, hi = est$F1_L_hi, n_pools = est$completed),
  data.frame(layer = "estimate", attacker = est$attacker, metric = "F1_J",
             value = est$F1_J_mean, lo = est$F1_J_lo, hi = est$F1_J_hi, n_pools = est$completed),
  # The analytic one-bucket baseline is a reference line, not an attacker row.
  # Its value is the mean of the per-pool baselines (they range 0.13-0.25).
  data.frame(layer = "baseline", attacker = "Analytic one-bucket", metric = c("F1_L", "F1_J"),
             value = c(bas$F1_L_mean, bas$F1_J_mean), lo = NA, hi = NA, n_pools = bas$completed)
)
plot_data$post_hoc <- plot_data$attacker == "Embedding (post-hoc exploratory)"

# ---- Plot -------------------------------------------------------------------
attacker_panel <- function(which_metric, x_title) {
  est <- subset(plot_data, layer == "estimate" & metric == which_metric)
  bas <- subset(plot_data, layer == "baseline" & metric == which_metric)
  est$attacker <- factor(est$attacker, levels = attackers)  # first level = bottom row

  ggplot(est, aes(x = value, y = attacker)) +
    geom_vline(xintercept = bas$value, linetype = "dashed",
               linewidth = ref_linewidth, colour = baseline_grey) +
    geom_linerange(aes(xmin = lo, xmax = hi, colour = attacker), linewidth = ci_linewidth) +
    geom_point(aes(colour = attacker, fill = attacker, shape = attacker),
               size = point_size, stroke = point_stroke) +
    scale_colour_manual(values = attacker_colour) +
    scale_fill_manual(values = attacker_fill) +
    scale_shape_manual(values = attacker_shape) +
    scale_y_discrete(labels = attacker_label) +
    scale_x_continuous(limits = c(0, 1), breaks = seq(0, 1, 0.25), labels = axis_01_labels) +
    labs(x = x_title, y = NULL) +
    theme_paper()
}

panel_a <- attacker_panel("F1_L", expression("Linkage " * (F1[L])))
panel_b <- attacker_panel("F1_J", expression("Joint reconstruction " * (F1[J])))

# Stacked so each panel gets the full column width.
fig <- panel_a / panel_b + plot_annotation(tag_levels = list(c("(a)", "(b)")))

# ---- Export -----------------------------------------------------------------
save_figure(fig, "fig1_headline_attackers", width = col_width, height = 2.2, data = plot_data)
