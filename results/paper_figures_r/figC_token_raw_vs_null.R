# figC_token_raw_vs_null.R
# Appendix Figure C: POST-HOC EXPLORATORY (D16). Raw visible joint score V_J
# against its oracle-size random-shuffle null, per arm, one-shot Sonnet. It
# shows what A_VJ ~ 0 means in raw terms: in the token arm the observed score
# is close to what randomly dealing the tokens into seven true-size groups gets.
#
# Run from the repository root:
#   Rscript results/paper_figures_r/figC_token_raw_vs_null.R

source("results/paper_figures_r/theme_paper.R")

# ---- Data -------------------------------------------------------------------
# Per-pool observed V_J and null mean (10,000 permutations per pool x arm),
# from the frozen D16 analysis. Arm means are plain means over the 20 pools.
pools <- read.csv("results/single_token_edge/analysis/per_pool.csv")
pools <- pools[pools$attacker == "One-shot Sonnet", ]

per_pool <- rbind(
  data.frame(layer = "pool", arm = pools$condition, pool = pools$pool,
             series = "observed", value = pools$V_J),
  data.frame(layer = "pool", arm = pools$condition, pool = pools$pool,
             series = "null", value = pools$null_oracle_V_J)
)
arm_means <- aggregate(value ~ arm + series, data = per_pool, FUN = mean)
arm_means$layer <- "arm_mean"
arm_means$pool  <- NA

plot_data <- rbind(per_pool, arm_means[, names(per_pool)])
plot_data$post_hoc <- TRUE

# ---- Plot -------------------------------------------------------------------
d <- plot_data
d$series <- factor(d$series, levels = c("observed", "null"))
d$arm    <- factor(d$arm, levels = c("sentence", "token"))
dodge    <- position_dodge(width = 0.5)

fig <- ggplot(d, aes(x = arm, y = value, shape = series, colour = series, fill = series)) +
  geom_point(data = subset(d, layer == "pool"), alpha = 0.35, size = 0.7, stroke = 0.3,
             position = position_jitterdodge(jitter.width = 0.12, dodge.width = 0.5, seed = 1)) +
  geom_point(data = subset(d, layer == "arm_mean"), size = point_size + 0.3,
             stroke = point_stroke + 0.2, position = dodge) +
  scale_colour_manual(values = null_colour, labels = null_label) +
  scale_fill_manual(values = null_fill, labels = null_label) +
  scale_shape_manual(values = null_shape, labels = null_label) +
  scale_x_discrete(labels = c(sentence = "Sentence", token = "Single token")) +
  scale_y_continuous(limits = c(0, 1), breaks = seq(0, 1, 0.25), labels = axis_01_labels) +
  labs(x = NULL, y = expression("Raw visible joint score " * (italic(V)[J])),
       shape = NULL, colour = NULL, fill = NULL) +
  theme_paper() +
  theme(legend.position = "top", legend.justification = "left",
        legend.margin = margin(0, 0, 0, 0), legend.box.spacing = unit(2, "pt"))

# ---- Export -----------------------------------------------------------------
save_figure(fig, "figC_token_raw_vs_null", width = col_width, height = 2.0, data = plot_data)
