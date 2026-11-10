# fig6_granularity_gradient.R
# The five-point granularity series on identical text, and what it means in
# words of the original document.
#
# (a) Null-adjusted VISIBLE joint reconstruction, A_VJ, the metric D16 froze as
#     PRIMARY. The id-level A_J is shown as a faint robustness series: the two
#     agree where duplicate fragment text is rare and diverge at one word, which
#     is the whole reason the visible scorer is primary.
# (b) How much of the 76-word excerpt comes back as ONE contiguous stretch, in
#     words, against the floor that the cut leaks by construction.
#
# Sources, all frozen artifacts:
#   sentence / token arms   results/single_token_edge/analysis/summary.json (D16)
#   4 / 3 / 2-word arms     results/gradient/visible_analysis/summary.json (D18)
#   id-level A_J            results/final/gradientJ/REPORT.txt values, carried in
#                           the data frame below and checked by validate_figures.R
#   recovery                results/gradient/recovery.json
#
# POST-HOC EXPLORATORY (D16, D18). One corpus, one model, one cut family.

source("results/paper_figures_r/theme_paper.R")
suppressPackageStartupMessages(library(jsonlite))

d16 <- fromJSON("results/single_token_edge/analysis/summary.json")
d18 <- fromJSON("results/gradient/visible_analysis/summary.json")
rec <- fromJSON("results/gradient/recovery.json")
s16 <- d16$attackers[["One-shot Sonnet"]]$means

arm_order <- c("1-word", "2-word", "3-word", "4-word", "sentence")
key16 <- c("sentence" = "sentence", "1-word" = "token")
key18 <- c("4-word" = "w4", "3-word" = "w3", "2-word" = "w2")

# id-level A_J, from the frozen scored reports (D16 analysis / D18 REPORT.txt)
a_j_id <- c("sentence" = 0.5387, "4-word" = 0.3127, "3-word" = 0.2178,
            "2-word" = 0.0812, "1-word" = -0.0165)

grab <- function(arm, field) {
  if (arm %in% names(key16)) s16[[key16[[arm]]]][[field]]
  else d18$arms[[key18[[arm]]]][[field]]
}

dat <- data.frame(
  arm        = arm_order,
  words      = vapply(arm_order, function(a) rec[[a]]$frags_per_doc, numeric(1)),
  frag_words = vapply(arm_order, function(a) rec[[a]]$doc_words / rec[[a]]$frags_per_doc,
                      numeric(1)),
  A_VJ       = vapply(arm_order, grab, numeric(1), field = "A_VJ"),
  V_J        = vapply(arm_order, grab, numeric(1), field = "V_J"),
  V_L        = vapply(arm_order, grab, numeric(1), field = "V_L"),
  A_VL       = vapply(arm_order, grab, numeric(1), field = "A_VL"),
  A_J_id     = a_j_id[arm_order],
  recovered  = vapply(arm_order, function(a) rec[[a]]$recovered_pct, numeric(1)),
  floor      = vapply(arm_order, function(a) rec[[a]]$floor_pct, numeric(1)),
  join       = vapply(arm_order, function(a) rec[[a]]$join_recall, numeric(1)),
  row.names  = NULL, stringsAsFactors = FALSE
)
dat$label <- sub("-word", "w", dat$arm)
dat$label[dat$arm == "sentence"] <- "sent"

x_breaks <- c(1, 2, 3, 4, 19)
x_labels <- c("1", "2", "3", "4", "19\n(sentence)")

# ---- (a) null-adjusted visible joint reconstruction ---------------------------
pa <- ggplot(dat, aes(frag_words, A_VJ)) +
  geom_hline(yintercept = 0, linewidth = ref_linewidth, colour = baseline_grey) +
  geom_line(aes(y = A_J_id), linewidth = ci_linewidth, colour = "grey70",
            linetype = "dotted") +
  geom_point(aes(y = A_J_id), size = point_size * 0.7, shape = 21,
             fill = "white", colour = "grey60", stroke = point_stroke * 0.8) +
  geom_line(linewidth = ci_linewidth, colour = sonnet_colour) +
  geom_point(size = point_size, shape = 21, fill = sonnet_colour,
             colour = sonnet_colour, stroke = point_stroke) +
  annotate("text", x = 6.2, y = 0.055, label = "id-level (robustness)",
           size = label_size, colour = "grey45", hjust = 0, family = font_family) +
  annotate("text", x = 1.08, y = 0.085, label = "visible text\n(primary)",
           size = label_size, colour = sonnet_colour, hjust = 0, vjust = 0,
           family = font_family, lineheight = 0.95) +
  annotate("text", x = 19, y = -0.055, label = "random-shuffle null",
           size = label_size, colour = baseline_grey, hjust = 1,
           family = font_family) +
  scale_x_log10(breaks = x_breaks, labels = x_labels) +
  scale_y_continuous(limits = c(-0.09, 0.66), breaks = seq(0, 0.6, 0.2)) +
  labs(x = NULL, y = "Null-adjusted joint\nreconstruction") +
  theme_paper()

# ---- (b) contiguous text recovered -------------------------------------------
pb <- ggplot(dat, aes(frag_words)) +
  geom_ribbon(aes(ymin = floor, ymax = recovered), fill = sonnet_colour, alpha = 0.13) +
  geom_line(aes(y = floor), linewidth = ci_linewidth, colour = baseline_grey,
            linetype = "dashed") +
  geom_line(aes(y = recovered), linewidth = ci_linewidth, colour = sonnet_colour) +
  geom_point(aes(y = recovered), size = point_size, shape = 21,
             fill = sonnet_colour, colour = sonnet_colour, stroke = point_stroke) +
  geom_point(aes(y = floor), size = point_size * 0.6, shape = 21,
             fill = baseline_grey, colour = baseline_grey, stroke = point_stroke * 0.8) +
  annotate("text", x = 6.2, y = 46, label = "attacker's contribution",
           size = label_size, colour = sonnet_colour, hjust = 0, family = font_family) +
  annotate("text", x = 6.2, y = 10, label = "leaked by the cut alone",
           size = label_size, colour = baseline_grey, hjust = 0, family = font_family) +
  scale_x_log10(breaks = x_breaks, labels = x_labels) +
  scale_y_continuous(limits = c(0, 70), breaks = seq(0, 60, 20),
                     labels = function(v) paste0(v, "%")) +
  labs(x = "Mean fragment length (words)",
       y = "Document recovered as one\ncontiguous stretch") +
  theme_paper()

fig <- pa / pb + plot_layout(heights = c(1, 1)) +
  plot_annotation(tag_levels = "a", tag_prefix = "(", tag_suffix = ")",
                  theme = theme(plot.margin = margin(2, 5, 2, 2)))

save_figure(fig, "fig6_granularity_gradient", col_width, 3.5, dat)
