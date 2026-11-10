# make_all.R
# Rebuild every paper figure, then run the validation checks.
#
# Run from the repository root:
#   Rscript results/paper_figures_r/make_all.R

scripts <- c("fig1_headline_attackers.R", "fig2_grid_reconstruction.R",
             "fig3_linkage_vs_ordering.R", "fig4_identifiers.R", "fig5_single_token.R",
             "fig6_granularity_gradient.R",
             "figA_gameO_vs_gameJ.R", "figB_resource_scaling.R", "figC_token_raw_vs_null.R")

for (s in scripts) source(file.path("results/paper_figures_r", s), local = new.env())

source("results/paper_figures_r/validate_figures.R", local = new.env())
