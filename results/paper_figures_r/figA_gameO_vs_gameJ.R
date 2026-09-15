# figA_gameO_vs_gameJ.R
# Appendix Figure A: ordering with membership given (Game O) against joint
# membership + order recovery (Game J), one-shot Sonnet. Prespecified.
#
# Game O is plotted as (1 + tau) / 2, the value F1_J takes when membership is
# perfect, so both games sit on one 0-1 scale. The transform is monotone, so
# the frozen tau CI maps directly. O and J are different units (documents vs
# pools) and different prompts, so the two markers are not joined.
#
# Run from the repository root:
#   Rscript results/paper_figures_r/figA_gameO_vs_gameJ.R

source("results/paper_figures_r/theme_paper.R")

# ---- Data -------------------------------------------------------------------
game_o   <- read.csv("results/final_analysis/TABLES/table_D_game_O.csv")
grid     <- read.csv("results/final_analysis/TABLES/table_C_grid_J.csv")
headline <- read.csv("results/final_analysis/TABLES/table_B_headline_J.csv")

o <- game_o[game_o$attacker == "One-shot Sonnet", ]
j <- rbind(
  data.frame(condition = "headline (full length)",
             headline[headline$attacker == "One-shot Sonnet", c("F1_J_mean", "F1_J_lo", "F1_J_hi", "completed")]),
  grid[grid$attacker == "One-shot Sonnet", c("condition", "F1_J_mean", "F1_J_lo", "F1_J_hi", "completed")]
)
j <- j[match(o$condition, j$condition), ]

split_condition <- function(condition) {
  ifelse(condition == "headline (full length)", "headline",
         sapply(strsplit(condition, " / ", fixed = TRUE), `[`, 1))
}
split_granularity <- function(condition) {
  ifelse(condition == "headline (full length)", "full length",
         sapply(strsplit(condition, " / ", fixed = TRUE), `[`, 2))
}

plot_data <- rbind(
  data.frame(condition = o$condition, game = "O",
             value = (1 + o$tau_mean) / 2, lo = (1 + o$tau_lo) / 2, hi = (1 + o$tau_hi) / 2,
             tau = o$tau_mean, tau_lo = o$tau_lo, tau_hi = o$tau_hi,
             n_units = o$docs, unit = "documents"),
  data.frame(condition = j$condition, game = "J",
             value = j$F1_J_mean, lo = j$F1_J_lo, hi = j$F1_J_hi,
             tau = NA, tau_lo = NA, tau_hi = NA,
             n_units = j$completed, unit = "pools")
)
plot_data$strategy    <- split_condition(plot_data$condition)
plot_data$granularity <- split_granularity(plot_data$condition)

# ---- Plot -------------------------------------------------------------------
d <- plot_data
d$strategy    <- factor(d$strategy, levels = c("headline", strategy_levels))
d$granularity <- factor(d$granularity, levels = rev(c("full length", granularity_levels)))
d$game        <- factor(d$game, levels = c("O", "J"))

fig <- ggplot(d, aes(x = value, y = granularity, colour = game, fill = game, shape = game)) +
  geom_linerange(aes(xmin = lo, xmax = hi), linewidth = ci_linewidth) +
  geom_point(size = point_size, stroke = point_stroke) +
  facet_grid(rows = vars(strategy), scales = "free_y", space = "free_y", switch = "y") +
  scale_colour_manual(values = game_colour, labels = game_label) +
  scale_fill_manual(values = game_colour, labels = game_label) +
  scale_shape_manual(values = game_shape, labels = game_label) +
  scale_y_discrete(labels = granularity_label) +
  scale_x_continuous(limits = c(0, 1), breaks = seq(0, 1, 0.25), labels = axis_01_labels) +
  labs(x = "Score (0-1)", y = NULL, colour = NULL, fill = NULL, shape = NULL) +
  theme_paper() +
  theme_strategy_strips() +
  # One legend entry per line, so it fits the column width.
  theme(legend.position = "top", legend.justification = "left", legend.direction = "vertical",
        legend.margin = margin(0, 0, 0, 0), legend.box.spacing = unit(2, "pt"))

# ---- Export -----------------------------------------------------------------
save_figure(fig, "figA_gameO_vs_gameJ", width = col_width, height = 3.0, data = plot_data)
