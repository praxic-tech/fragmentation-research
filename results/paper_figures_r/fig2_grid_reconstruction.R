# fig2_grid_reconstruction.R
# Figure 2 (main text): joint reconstruction across the nine retained
# strategy x granularity cells, one-shot Sonnet. Prespecified (grid pools 2-25).
#
# Run from the repository root:
#   Rscript results/paper_figures_r/fig2_grid_reconstruction.R

source("results/paper_figures_r/theme_paper.R")

# ---- Data -------------------------------------------------------------------
# Frozen grid summary: pool means with 95% percentile-bootstrap CIs (D13).
grid   <- read.csv("results/final_analysis/TABLES/table_C_grid_J.csv")
sonnet <- grid[grid$attacker == "One-shot Sonnet", ]
parts  <- do.call(rbind, strsplit(sonnet$condition, " / ", fixed = TRUE))

plot_data <- data.frame(
  condition       = sonnet$condition,
  strategy        = parts[, 1],
  granularity     = parts[, 2],
  F1_J            = sonnet$F1_J_mean,
  lo              = sonnet$F1_J_lo,
  hi              = sonnet$F1_J_hi,
  b_J             = sonnet$b_J_mean,      # analytic one-bucket baseline, mean over the cell's pools
  pools_completed = sonnet$completed,     # random / token-window: 23 (one non-completion)
  pools_attempted = sonnet$attempted
)

# ---- Plot -------------------------------------------------------------------
d <- plot_data
d$strategy    <- factor(d$strategy, levels = strategy_levels)
d$granularity <- factor(d$granularity, levels = rev(granularity_levels))  # sentence on top

fig <- ggplot(d, aes(y = granularity)) +
  # Baseline as a small grey tick on each row (0.128-0.132 across cells).
  geom_point(aes(x = b_J), shape = "|", size = 2.4, colour = baseline_grey) +
  geom_linerange(aes(xmin = lo, xmax = hi), colour = sonnet_colour, linewidth = ci_linewidth) +
  geom_point(aes(x = F1_J), shape = 21, colour = sonnet_colour, fill = sonnet_colour,
             size = point_size, stroke = point_stroke) +
  # Strategy groups become left-hand strips; the gap between facets is the separator.
  facet_grid(rows = vars(strategy), scales = "free_y", space = "free_y", switch = "y") +
  scale_y_discrete(labels = granularity_label) +
  scale_x_continuous(limits = c(0, 1), breaks = seq(0, 1, 0.25), labels = axis_01_labels) +
  labs(x = expression("Joint reconstruction " * (F1[J])), y = NULL) +
  theme_paper() +
  theme_strategy_strips()

# ---- Export -----------------------------------------------------------------
save_figure(fig, "fig2_grid_reconstruction", width = col_width, height = 2.4, data = plot_data)
