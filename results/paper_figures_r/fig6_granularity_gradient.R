# fig6_granularity_gradient.R
# The five-point granularity series on identical text, and what it means in
# words of the original document.
#
# (a) Visible joint reconstruction V_J against the RANDOM-SHUFFLE REFERENCE for
#     the same arm: the mean score of a random partition of that pool into the
#     true per-document fragment counts, 10,000 seeded permutations. The gap
#     between the two lines is the signal; A_VJ = (V_J - null)/(1 - null) is
#     that gap normalised, and is printed at each point because it is the
#     metric D16 froze as PRIMARY.
#
#     Plotting the reference explicitly matters here: it is NOT constant across
#     arms. It falls from 0.423 at the sentence cut to 0.141 at one word, so
#     raw V_J is not comparable between arms and a reader who eyeballs the blue
#     line alone will over-read the decline.
#
# (b) How much of the 76-word excerpt comes back as ONE contiguous stretch, in
#     words, against the floor that the cut leaks by construction.
#
# Sources, all frozen artifacts:
#   sentence / token arms   results/single_token_edge/analysis/{summary.json,per_pool.csv}
#   4 / 3 / 2-word arms     results/gradient/visible_analysis/summary.json
#   recovery                results/gradient/recovery.json
#
# POST-HOC EXPLORATORY (D16, D18). One corpus, one model, one cut family.

source("results/paper_figures_r/theme_paper.R")
suppressPackageStartupMessages(library(jsonlite))

d16 <- fromJSON("results/single_token_edge/analysis/summary.json")
d18 <- fromJSON("results/gradient/visible_analysis/summary.json")
rec <- fromJSON("results/gradient/recovery.json")
s16 <- d16$attackers[["One-shot Sonnet"]]$means
pp  <- read.csv("results/single_token_edge/analysis/per_pool.csv")
pp  <- pp[pp$attacker == "One-shot Sonnet", ]

arm_order <- c("1-word", "2-word", "3-word", "4-word", "sentence")
key16 <- c("sentence" = "sentence", "1-word" = "token")
key18 <- c("4-word" = "w4", "3-word" = "w3", "2-word" = "w2")

a_j_id <- c("sentence" = 0.5387, "4-word" = 0.3127, "3-word" = 0.2178,
            "2-word" = 0.0812, "1-word" = -0.0165)   # frozen scored reports

grab <- function(arm, field) {
  if (arm %in% names(key16)) s16[[key16[[arm]]]][[field]] else d18$arms[[key18[[arm]]]][[field]]
}
null_vj <- function(arm) {
  if (arm %in% names(key16)) mean(pp$null_oracle_V_J[pp$condition == key16[[arm]]])
  else d18$arms[[key18[[arm]]]]$null_oracle_V_J
}

dat <- data.frame(
  arm        = arm_order,
  frag_words = vapply(arm_order, function(a) rec[[a]]$doc_words / rec[[a]]$frags_per_doc, numeric(1)),
  frags_pool = vapply(arm_order, function(a) rec[[a]]$frags_per_doc * 7, numeric(1)),
  V_J        = vapply(arm_order, grab, numeric(1), field = "V_J"),
  V_L        = vapply(arm_order, grab, numeric(1), field = "V_L"),
  A_VJ       = vapply(arm_order, grab, numeric(1), field = "A_VJ"),
  A_VL       = vapply(arm_order, grab, numeric(1), field = "A_VL"),
  null_V_J   = vapply(arm_order, null_vj, numeric(1)),
  A_J_id     = a_j_id[arm_order],
  recovered  = vapply(arm_order, function(a) rec[[a]]$recovered_pct, numeric(1)),
  floor      = vapply(arm_order, function(a) rec[[a]]$floor_pct, numeric(1)),
  join       = vapply(arm_order, function(a) rec[[a]]$join_recall, numeric(1)),
  row.names  = NULL, stringsAsFactors = FALSE
)

x_breaks <- c(1, 2, 3, 4, 19)
x_labels <- c("1", "2", "3", "4", "19\n(sentence)")

# ---- (a) observed against the random-shuffle reference -----------------------
pa <- ggplot(dat, aes(frag_words)) +
  geom_ribbon(aes(ymin = null_V_J, ymax = V_J), fill = sonnet_colour, alpha = 0.11) +
  geom_line(aes(y = null_V_J), linewidth = ci_linewidth, colour = baseline_grey,
            linetype = "dashed") +
  geom_point(aes(y = null_V_J), size = point_size * 0.6, shape = 21,
             fill = baseline_grey, colour = baseline_grey, stroke = point_stroke * 0.8) +
  geom_line(aes(y = V_J), linewidth = ci_linewidth, colour = sonnet_colour) +
  geom_point(aes(y = V_J), size = point_size, shape = 21, fill = sonnet_colour,
             colour = sonnet_colour, stroke = point_stroke) +
  geom_text(aes(y = V_J, label = sprintf("%.2f", A_VJ)), vjust = -1.25,
            size = label_size, colour = sonnet_colour, family = font_family) +
  annotate("text", x = 1.05, y = 0.655, label = "observed", size = label_size,
           colour = sonnet_colour, hjust = 0, family = font_family) +
  annotate("text", x = 1.05, y = 0.055, label = "random-shuffle reference",
           size = label_size, colour = baseline_grey, hjust = 0, family = font_family) +
  annotate("text", x = 19, y = 0.655, label = "paste('labels: ', A[VJ])", parse = TRUE,
           size = label_size, colour = sonnet_colour, hjust = 1, family = font_family) +
  scale_x_log10(breaks = x_breaks, labels = x_labels) +
  scale_y_continuous(limits = c(0, 0.92), breaks = seq(0, 0.8, 0.2)) +
  labs(x = "Mean fragment length (words)", y = "Visible joint\nreconstruction") +
  theme_paper()

# ---- (b) contiguous text recovered -------------------------------------------
pb <- ggplot(dat, aes(frag_words)) +
  geom_ribbon(aes(ymin = floor, ymax = recovered), fill = sonnet_colour, alpha = 0.11) +
  geom_line(aes(y = floor), linewidth = ci_linewidth, colour = baseline_grey,
            linetype = "dashed") +
  geom_point(aes(y = floor), size = point_size * 0.6, shape = 21,
             fill = baseline_grey, colour = baseline_grey, stroke = point_stroke * 0.8) +
  geom_line(aes(y = recovered), linewidth = ci_linewidth, colour = sonnet_colour) +
  geom_point(aes(y = recovered), size = point_size, shape = 21, fill = sonnet_colour,
             colour = sonnet_colour, stroke = point_stroke) +
  annotate("text", x = 5.6, y = 47, label = "attacker's contribution", size = label_size,
           colour = sonnet_colour, hjust = 0, family = font_family) +
  annotate("text", x = 5.6, y = 9, label = "leaked by the cut alone", size = label_size,
           colour = baseline_grey, hjust = 0, family = font_family) +
  scale_x_log10(breaks = x_breaks, labels = x_labels) +
  scale_y_continuous(limits = c(0, 72), breaks = seq(0, 60, 20),
                     labels = function(v) paste0(v, "%")) +
  labs(x = "Mean fragment length (words)",
       y = "Document recovered as one\ncontiguous stretch") +
  theme_paper()

# Side by side at page width: a spanning float, so the width is already paid
# for, and stacked in one column the same two panels were twice as tall.
fig <- (pa | pb) +
  plot_annotation(tag_levels = "a", tag_prefix = "(", tag_suffix = ")",
                  theme = theme(plot.margin = margin(2, 5, 2, 2)))

save_figure(fig, "fig6_granularity_gradient", page_width, 2.1, dat)
