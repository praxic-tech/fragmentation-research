# fig4_identifiers.R
# Figure 4 (main text): synthetic identifier records, Game J, 20 pools.
# Panel (a), F1_J, is prespecified (D11). Panel (b), linkage precision against
# template-respecting chance, is an EXPLORATORY post-hoc diagnostic from the
# frozen analysis package (table E3); it is not the prespecified endpoint.
#
# Run from the repository root:
#   Rscript results/paper_figures_r/fig4_identifiers.R

source("results/paper_figures_r/theme_paper.R")

# ---- Data -------------------------------------------------------------------
ident  <- read.csv("results/final_analysis/TABLES/table_E_identifier_J.csv")
member <- read.csv("results/final_analysis/TABLES/table_E3_identifier_membership.csv")

rows <- c("Random partition", "Memon-inspired", "Embedding (post-hoc exploratory)", "One-shot Sonnet")
source_name <- c("Random partition" = "Random", "Memon-inspired" = "Memon-inspired",
                 "Embedding (post-hoc exploratory)" = "Embedding (post-hoc exploratory)",
                 "One-shot Sonnet" = "One-shot Sonnet")

e  <- ident[match(source_name[rows], ident$attacker), ]
e3 <- member[match(source_name[rows], member$attacker), ]

plot_data <- rbind(
  data.frame(panel = "a", layer = "estimate", row = rows, metric = "F1_J",
             value = e$F1_J_mean, lo = e$F1_J_lo, hi = e$F1_J_hi, n_pools = e$completed),
  data.frame(panel = "b", layer = "estimate", row = rows, metric = "linkage_precision",
             value = e3$linkage_precision_mean, lo = e3$lo, hi = e3$hi, n_pools = e$completed),
  # Reference lines, read from the frozen tables rather than typed in.
  data.frame(panel = "a", layer = "reference", row = c("analytic baseline", "schema-order baseline"),
             metric = "F1_J",
             value = c(ident$F1_J_mean[ident$attacker == "Analytic one-bucket"],
                       ident$F1_J_mean[ident$attacker == "Schema-order"]),
             lo = NA, hi = NA, n_pools = 20),
  data.frame(panel = "b", layer = "reference", row = "template-respecting chance",
             metric = "linkage_precision", value = member$template_chance[1],
             lo = NA, hi = NA, n_pools = 20)
)
plot_data$post_hoc <- plot_data$row == "Embedding (post-hoc exploratory)" | plot_data$panel == "b"

# ---- Plot -------------------------------------------------------------------
# The axis runs 0-0.3, not 0-1: every estimate and reference lies below 0.25,
# and at 0-1 the comparison with the reference lines (the result) is not
# readable. The axis still starts at zero.
x_max <- 0.3

identifier_panel <- function(which_panel, x_title) {
  est <- subset(plot_data, panel == which_panel & layer == "estimate")
  ref <- subset(plot_data, panel == which_panel & layer == "reference")
  est$row <- factor(est$row, levels = rows)

  ggplot(est, aes(x = value, y = row)) +
    geom_vline(data = ref, aes(xintercept = value, linetype = row),
               linewidth = ref_linewidth, colour = baseline_grey) +
    # Short direct labels on the reference lines, above the top row.
    annotate("text", x = ref$value, y = length(rows) + 0.75, label = reference_label[ref$row],
             size = label_size, colour = baseline_grey, hjust = -0.08, vjust = 0) +
    geom_linerange(aes(xmin = lo, xmax = hi, colour = row), linewidth = ci_linewidth) +
    geom_point(aes(colour = row, fill = row, shape = row), size = point_size, stroke = point_stroke) +
    scale_colour_manual(values = attacker_colour) +
    scale_fill_manual(values = attacker_fill) +
    scale_shape_manual(values = attacker_shape) +
    scale_linetype_manual(values = reference_linetype) +
    scale_y_discrete(labels = attacker_label, expand = expansion(add = c(0.6, 1.1))) +
    scale_x_continuous(limits = c(0, x_max), breaks = seq(0, x_max, 0.1),
                       labels = c("0", "0.1", "0.2", "0.3")) +
    coord_cartesian(clip = "off") +
    labs(x = x_title, y = NULL) +
    theme_paper()
}

panel_a <- identifier_panel("a", expression("Joint reconstruction " * (F1[J])))
panel_b <- identifier_panel("b", "Linkage precision")   # defined in the caption

fig <- panel_a / panel_b + plot_annotation(tag_levels = list(c("(a)", "(b)")))

# ---- Export -----------------------------------------------------------------
save_figure(fig, "fig4_identifiers", width = col_width, height = 2.6, data = plot_data)
