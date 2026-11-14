# fig7_headline_ladder.R
# Figure 7 (full width): headline prose, Game J, (a) F1_J and (b) F1_L on the 46 headline pools for every
# attacker (prespecified, with tier 0 and tier 3 from D19) and every model of
# the post-hoc Sonnet-dependence sweep. Post hoc = open marker. A sweep model
# refused under the preregistered rule is grey, and its value is over the
# units it answered (secondary).
#
# Run from the repository root:
#   Rscript results/paper_figures_r/fig7_headline_ladder.R

source("results/paper_figures_r/theme_paper.R")

# ---- Data -------------------------------------------------------------------
# results/final_analysis/TABLES/table_B3_headline_ladder.csv, written by
# analysis/cross_model_ladder.py. Nothing is recomputed here.
L <- read.csv("results/final_analysis/TABLES/table_B3_headline_ladder.csv",
              stringsAsFactors = FALSE)

group_of <- function(kind) ifelse(grepl("sweep", kind), "Other LLMs\n(post hoc)",
                                  ifelse(grepl("baseline", kind), "baseline", "Attackers"))
est <- L[L$kind != "baseline", ]
bas <- L[L$kind == "baseline", ]

display <- c("T0-PUP" = "Tier 0, PUP", "Memon-inspired" = "Memon-inspired",
             "Embedding (post-hoc exploratory)" = "Embedding (post hoc)",
             "T0-classical" = "Tier 0, classical", "T3-crossenc" = "Tier 3, cross-encoder",
             "One-shot Sonnet" = "One-shot Sonnet 5",
             "gpt-oss-20b" = "gpt-oss-20b", "llama-4-maverick" = "Llama 4 Maverick",
             "gpt-4.1" = "GPT-4.1", "gemma-4-12b" = "Gemma 4 12B",
             "deepseek-v3.2" = "DeepSeek-V3.2", "gpt-5.6-sol" = "GPT-5.6 sol")

plot_data <- data.frame(
  attacker = est$attacker,
  label    = paste0(display[est$attacker],
                    ifelse(!is.na(est$verdict) & est$verdict == "REFUSED", " (refused)", "")),
  group    = group_of(est$kind),
  value = est$F1_J, lo = est$F1_J_lo, hi = est$F1_J_hi,
  value_L = est$F1_L, lo_L = est$F1_L_lo, hi_L = est$F1_L_hi, n_pools = est$answered,
  verdict  = ifelse(is.na(est$verdict) | est$verdict == "", "", est$verdict),
  post_hoc = grepl("post hoc", est$kind),
  stringsAsFactors = FALSE)
plot_data$style <- ifelse(plot_data$verdict == "REFUSED", "refused",
                   ifelse(plot_data$attacker == "One-shot Sonnet", "sonnet",
                   ifelse(grepl("sweep", est$kind), "other_llm", "attacker")))

# Rows sorted by F1_J within each group, lowest at the bottom.
plot_data <- plot_data[order(plot_data$group, plot_data$value), ]
plot_data$label <- factor(plot_data$label, levels = unique(plot_data$label))
plot_data$group <- factor(plot_data$group, levels = c("Other LLMs\n(post hoc)", "Attackers"))

style_colour <- c(attacker = "#D55E00", sonnet = sonnet_colour, other_llm = "#CC79A7",
                  refused = "grey55")

# ---- Plot -------------------------------------------------------------------
ladder_panel <- function(v, lo, hi, base, sonnet, x_title, show_y) {
  d <- plot_data; d$v <- d[[v]]; d$l <- d[[lo]]; d$h <- d[[hi]]
  ggplot(d, aes(x = v, y = label)) +
    geom_vline(xintercept = base, linetype = "dashed",
               linewidth = ref_linewidth, colour = baseline_grey) +
    geom_vline(xintercept = sonnet, linetype = "dotted",
               linewidth = ref_linewidth, colour = sonnet_colour) +
    geom_linerange(aes(xmin = l, xmax = h, colour = style), linewidth = ci_linewidth) +
    geom_point(aes(colour = style, fill = ifelse(post_hoc, "white", style_colour[style])),
               shape = 21, size = point_size, stroke = point_stroke) +
    scale_colour_manual(values = style_colour) +
    scale_fill_identity() +
    facet_grid(group ~ ., scales = "free_y", space = "free_y", switch = "y") +
    scale_x_continuous(limits = c(0, 1), breaks = seq(0, 1, 0.25), labels = axis_01_labels) +
    labs(x = x_title, y = NULL) +
    theme_paper() + theme_strategy_strips() +
    (if (show_y) theme() else theme(axis.text.y = element_blank(), strip.text.y.left = element_blank()))
}
son <- L[L$attacker == "One-shot Sonnet", ]
panel_a <- ladder_panel("value", "lo", "hi", bas$F1_J, son$F1_J,
                        expression("Joint reconstruction" ~ (F1[J])), TRUE)
panel_b <- ladder_panel("value_L", "lo_L", "hi_L", bas$F1_L, son$F1_L,
                        expression("Linkage" ~ (F1[L])), FALSE)
fig <- panel_a + panel_b + plot_annotation(tag_levels = list(c("(a)", "(b)")))

# ---- Export -----------------------------------------------------------------
save_figure(fig, "fig7_headline_ladder", width = page_width, height = 2.3,
            data = plot_data[, c("attacker", "label", "group", "value", "lo", "hi",
                                 "value_L", "lo_L", "hi_L", "n_pools", "verdict", "post_hoc", "style")])
