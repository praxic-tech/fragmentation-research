# fig3_linkage_vs_ordering.R
# Figure 3 (main text): the two components of Game J, F1_J = F1_L x q, for the
# nine retained cells, one-shot Sonnet. Prespecified (grid pools 2-25).
#
# One column, panels stacked. Do not widen it back to page_width: as a
# figure* it could only be set at a page top or bottom, and it was what
# forced a float-only page in Section 5.
#
# Run from the repository root:
#   Rscript results/paper_figures_r/fig3_linkage_vs_ordering.R

source("results/paper_figures_r/theme_paper.R")

# ---- Data -------------------------------------------------------------------
# Frozen grid summary (D13). q is micro-averaged (sum C / sum K) with its
# bootstrap CI; b_L is the analytic one-bucket linkage baseline of each cell.
grid     <- read.csv("results/final_analysis/TABLES/table_C_grid_J.csv")
sonnet   <- grid[grid$attacker == "One-shot Sonnet", ]
analytic <- grid[grid$attacker == "Analytic one-bucket", ]
analytic <- analytic[match(sonnet$condition, analytic$condition), ]
parts    <- do.call(rbind, strsplit(sonnet$condition, " / ", fixed = TRUE))

plot_data <- rbind(
  data.frame(condition = sonnet$condition, strategy = parts[, 1], granularity = parts[, 2],
             metric = "F1_L", value = sonnet$F1_L_mean, lo = sonnet$F1_L_lo, hi = sonnet$F1_L_hi,
             reference = analytic$F1_L_mean, pools_completed = sonnet$completed),
  data.frame(condition = sonnet$condition, strategy = parts[, 1], granularity = parts[, 2],
             metric = "q", value = sonnet$q_micro, lo = sonnet$q_micro_lo, hi = sonnet$q_micro_hi,
             reference = 0.5, pools_completed = sonnet$completed)   # 0.5 = chance direction
)

# ---- Plot -------------------------------------------------------------------
component_panel <- function(which_metric, x_title) {
  d <- subset(plot_data, metric == which_metric)
  d$strategy    <- factor(d$strategy, levels = strategy_levels)
  d$granularity <- factor(d$granularity, levels = rev(granularity_levels))

  p <- ggplot(d, aes(y = granularity)) +
    geom_linerange(aes(xmin = lo, xmax = hi), colour = sonnet_colour, linewidth = ci_linewidth) +
    geom_point(aes(x = value), shape = 21, colour = sonnet_colour, fill = sonnet_colour,
               size = point_size, stroke = point_stroke) +
    facet_grid(rows = vars(strategy), scales = "free_y", space = "free_y", switch = "y") +
    scale_y_discrete(labels = granularity_label) +
    scale_x_continuous(limits = c(0, 1), breaks = seq(0, 1, 0.25), labels = axis_01_labels) +
    labs(x = x_title, y = NULL) +
    theme_paper() +
    theme_strategy_strips()

  # Reference drawn underneath the estimates: per-row baseline ticks for F1_L,
  # one chance line for q.
  if (which_metric == "F1_L") {
    p$layers <- c(geom_point(aes(x = reference), shape = "|", size = 2.4, colour = baseline_grey),
                  p$layers)
  } else {
    p$layers <- c(geom_vline(xintercept = 0.5, linetype = "dashed",
                             linewidth = ref_linewidth, colour = baseline_grey),
                  p$layers)
  }
  p
}

panel_a <- component_panel("F1_L", expression("Linkage " * (F1[L])))
# Stacked, not side by side: a one-column figure can be set inside a column,
# which a figure* cannot, and it matches every other two-panel figure here.
# Panel (b) keeps its own row labels and strategy strips because it is no
# longer beside panel (a).
panel_b <- component_panel("q", expression("Direction accuracy on correct links " * (italic(q))))

fig <- (panel_a / panel_b) + plot_annotation(tag_levels = list(c("(a)", "(b)")))

# ---- Export -----------------------------------------------------------------
save_figure(fig, "fig3_linkage_vs_ordering", width = col_width, height = 4.2, data = plot_data)
