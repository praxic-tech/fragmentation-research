# figB_resource_scaling.R
# Appendix Figure B: output tokens of the answering call against fragment
# count, for every one-shot Game J unit. Prespecified units plus the post-hoc
# single-token arm (D16), drawn with open markers.
#
# "Answering call" = the call whose answer was scored. For prespecified units
# this is MASTER_RESULTS.answer_call_output_tokens. For the single-token arm it
# is read from the provider records: the last attempt that returned a model
# answer (8 units were answered by their repair call; for 3, the repair call
# exhausted 128k and the unit kept its first answer). This is a plotting-input
# correction to the matplotlib figure, which used the first call for all 20;
# no reported result changes.
#
# Run from the repository root:
#   Rscript results/paper_figures_r/figB_resource_scaling.R

source("results/paper_figures_r/theme_paper.R")

read_jsonl <- function(path) {
  lapply(readLines(path, encoding = "UTF-8", warn = FALSE), jsonlite::fromJSON, simplifyVector = FALSE)
}

# ---- Data: prespecified units -------------------------------------------------
master <- read.csv("results/final_analysis/MASTER_RESULTS.csv")
pre <- master[master$attacker == "One-shot Sonnet" & master$game == "J", ]
prespecified <- data.frame(
  set           = paste(pre$family, "J"),
  unit          = pre$unit_id,
  cell          = pre$cell,
  n_fragments   = pre$n_fragments,
  output_tokens = pre$answer_call_output_tokens,
  rbnc          = pre$rbnc %in% c(TRUE, "True"),
  answering_call = "as recorded in MASTER_RESULTS",
  post_hoc      = FALSE
)

# ---- Data: post-hoc single-token arm -------------------------------------------
usage <- list()
for (f in c("results/batches/single-token-edge-J.results.jsonl",
            "results/batches/single-token-edge-J-r1.results.jsonl")) {
  for (r in read_jsonl(f)) usage[[r$custom_id]] <- r$usage$output_tokens
}
token_rows <- read_jsonl("results/final/singleTokenEdgeJ/edge__token/J.jsonl")
token <- do.call(rbind, lapply(token_rows, function(r) {
  answered <- Filter(function(a) is.null(a$error), r$repair$attempts)   # attempts with a model answer
  call_id  <- answered[[length(answered)]]$custom_id
  data.frame(set = "single-token arm", unit = r$unit, cell = "edge__token",
             n_fragments = r$n_fragments, output_tokens = usage[[call_id]], rbnc = FALSE,
             answering_call = call_id, post_hoc = TRUE)
}))

plot_data <- rbind(prespecified, token)
plot_data$set <- factor(plot_data$set, levels = resource_sets)

# ---- Plot -------------------------------------------------------------------
budget <- 128000
rbnc   <- subset(plot_data, rbnc)

fig <- ggplot(plot_data, aes(x = n_fragments, y = output_tokens / 1000)) +
  geom_hline(yintercept = budget / 1000, linetype = "dashed",
             linewidth = ref_linewidth, colour = baseline_grey) +
  annotate("text", x = 700, y = budget / 1000, label = "128k output budget",
           size = label_size, colour = baseline_grey, hjust = 1, vjust = -0.5) +
  geom_point(aes(shape = set, fill = set), colour = "grey20", size = 1.1, stroke = 0.35) +
  # The one resource-bounded non-completion, ringed and labelled.
  geom_point(data = rbnc, shape = 21, fill = NA, colour = "black", size = 3.2, stroke = 0.5) +
  annotate("text", x = rbnc$n_fragments, y = budget / 1000 + 8,
           label = "non-completion", size = label_size, hjust = 0.5) +
  scale_shape_manual(values = resource_shape, labels = resource_label) +
  scale_fill_manual(values = resource_fill, labels = resource_label) +
  scale_x_continuous(limits = c(0, 700), breaks = seq(0, 700, 100), expand = expansion(mult = 0.01)) +
  scale_y_continuous(limits = c(0, 140), breaks = seq(0, 140, 20), expand = expansion(mult = 0.01)) +
  labs(x = "Fragments in pool", y = "Output tokens of answering call (thousands)",
       shape = NULL, fill = NULL) +
  theme_paper() +
  # Legend above the panel: inside it, it would cover data points.
  theme(legend.position = "top", legend.justification = "left",
        legend.margin = margin(0, 0, 0, 0), legend.box.spacing = unit(2, "pt")) +
  guides(shape = guide_legend(ncol = 2), fill = guide_legend(ncol = 2))

# ---- Export -----------------------------------------------------------------
save_figure(fig, "figB_resource_scaling", width = col_width, height = 2.8, data = plot_data)
