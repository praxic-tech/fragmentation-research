# theme_paper.R
# Shared look for every paper figure: sizes, palette, theme and export.
# Every figure script sources this file. Change a value here to change it in
# every figure.

suppressPackageStartupMessages({
  library(ggplot2)
  library(patchwork)
  library(sysfonts)
  library(showtext)
})

fig_dir <- "results/paper_figures_r"

# ---- Paper geometry (ACM sigconf) -------------------------------------------
# acmart sigconf sets \columnwidth to 241.14749pt = 3.337in; 3.33 is that width.
col_width  <- 3.33   # inches, one column
page_width <- 7.0    # inches, full text width (figure*)

# ---- Typography --------------------------------------------------------------
# The paper is acmart, which sets its text in Linux Libertine with Linux
# Biolinum as the matching sans; Biolinum is what the template uses for headings
# and captions, so figure text is set in it too.
#
# WHY showtext AND NOT cairo_pdf's own font lookup. On Windows, grDevices'
# cairo_pdf resolves families through GDI, which cannot use these CFF-flavoured
# OTFs: every family string ("Linux Biolinum O", "LinBiolinumO", ...) silently
# falls back to ArialMT, confirmed with pdffonts. systemfonts::register_font
# does not help either -- that registry feeds svglite and ragg, not cairo.
# showtext draws the real glyph outlines on any device, so the shapes are
# genuinely Biolinum. The consequence, stated plainly: text in the PDF is
# OUTLINES, not selectable text. pdffonts on the output therefore lists no
# fonts at all, which passes any embedding requirement trivially.
# Verified: at 8pt the cap height is identical whether showtext_opts(dpi=) is
# 72, 96 or 300, so there is no silent scaling.
font_dirs <- c(file.path(Sys.getenv("LOCALAPPDATA"), "Microsoft/Windows/Fonts"),
               file.path(Sys.getenv("LOCALAPPDATA"),
                         "Programs/MiKTeXp/fonts/opentype/public/libertine"),
               "/usr/share/fonts/opentype/linux-libertine",
               "/usr/share/texmf/fonts/opentype/public/libertine")
find_font <- function(file) {
  hit <- file.path(font_dirs, file)
  hit <- hit[file.exists(hit)]
  if (!length(hit)) stop("font not found: ", file,
                         "\nLooked in:\n  ", paste(font_dirs, collapse = "\n  "),
                         "\nInstall the libertine package (TeX Live / MiKTeX) or the ",
                         "Linux Libertine O and Linux Biolinum O fonts.")
  hit[1]
}
font_add("Biolinum",
         regular    = find_font("LinBiolinum_R.otf"),
         bold       = find_font("LinBiolinum_RB.otf"),
         italic     = find_font("LinBiolinum_RI.otf"),
         bolditalic = find_font("LinBiolinum_RBO.otf"))
font_add("Libertine",
         regular = find_font("LinLibertine_R.otf"),
         bold    = find_font("LinLibertine_RB.otf"),
         italic  = find_font("LinLibertine_RI.otf"))
showtext_auto()

font_family <- "Biolinum"        # matching sans of the paper's Libertine text
math_family <- "Libertine"       # italic serif for F1_J, tau, q
base_size   <- 8     # axis titles, panel tags (pt)
tick_size   <- 7     # tick labels, strips, legends (pt)
label_size  <- 6 / .pt   # direct labels drawn with annotate(): 6 pt, in ggplot's mm units
ink         <- "grey15"

# ---- Marks -------------------------------------------------------------------
point_size     <- 1.8
point_stroke   <- 0.5
ci_linewidth   <- 0.45
ref_linewidth  <- 0.3
axis_linewidth <- 0.25
baseline_grey  <- "grey55"

axis_01_labels <- c("0", "0.25", "0.5", "0.75", "1")   # for breaks = seq(0, 1, 0.25)

# ---- Attackers: one encoding for the whole paper -----------------------------
# Okabe-Ito hues (validated for colour-vision deficiency), and every attacker
# also has its own marker shape. Post-hoc exploratory = open (white-filled) marker.
sonnet_colour <- "#0072B2"

attacker_colour <- c("One-shot Sonnet"                  = sonnet_colour,
                     "Memon-inspired"                   = "#D55E00",
                     "Embedding (post-hoc exploratory)" = "#009E73",
                     "Random partition"                 = "grey45")
attacker_fill   <- c("One-shot Sonnet"                  = sonnet_colour,
                     "Memon-inspired"                   = "#D55E00",
                     "Embedding (post-hoc exploratory)" = "white",
                     "Random partition"                 = "grey45")
attacker_shape  <- c("One-shot Sonnet"                  = 21,   # circle
                     "Memon-inspired"                   = 22,   # square
                     "Embedding (post-hoc exploratory)" = 23,   # diamond
                     "Random partition"                 = 24)   # triangle (a baseline)
attacker_label  <- c("One-shot Sonnet"                  = "One-shot Sonnet",
                     "Memon-inspired"                   = "Memon-inspired",
                     "Embedding (post-hoc exploratory)" = "Embedding\n(post-hoc exploratory)",
                     "Random partition"                 = "Random partition\n(baseline)")

# ---- Reference lines (baselines are lines, never attacker rows) --------------
reference_linetype <- c("analytic baseline"          = "dashed",
                        "schema-order baseline"      = "solid",
                        "template-respecting chance" = "dotted")
reference_label    <- c("analytic baseline"          = "analytic",
                        "schema-order baseline"      = "schema order",
                        "template-respecting chance" = "1/7")

# ---- Grid conditions ---------------------------------------------------------
# Strategies from structure-blind to most disruptive; granularity coarse to fine.
strategy_levels    <- c("random", "semantic", "coherence-sever", "subject-verb")
granularity_levels <- c("sentence", "clause", "token-window")
granularity_label  <- c("sentence" = "sentence", "clause" = "clause",
                        "token-window" = "token window", "full length" = "full length")

# ---- Appendix A: Game O vs Game J ---------------------------------------------
game_colour <- c(O = "#56B4E9", J = sonnet_colour)
game_shape  <- c(O = 24, J = 21)
game_label  <- c(expression("Game O, membership given: " * (1 + tau) / 2),
                 expression("Game J: " * F1[J]))

# ---- Appendix B: resource sets -------------------------------------------------
resource_sets  <- c("headline J", "grid J", "identifier J", "single-token arm")
resource_shape <- c("headline J" = 21, "grid J" = 24, "identifier J" = 22, "single-token arm" = 23)
resource_fill  <- c("headline J" = "grey25", "grid J" = "grey70", "identifier J" = "grey50",
                    "single-token arm" = "white")
resource_label <- c("headline J" = "Headline J (46 pools)", "grid J" = "Grid J (216)",
                    "identifier J" = "Identifier J (20)",
                    "single-token arm" = "Single-token arm, post hoc (20)")

# ---- Appendix C: observed vs null ----------------------------------------------
null_colour <- c(observed = sonnet_colour, null = "grey40")
null_fill   <- c(observed = "white", null = "grey40")
null_shape  <- c(observed = 21, null = 23)
null_label  <- c(observed = "Observed", null = "Random-shuffle null (true group sizes)")

# ---- Theme --------------------------------------------------------------------
theme_paper <- function() {
  theme_classic(base_size = base_size, base_family = font_family) +
    theme(
      text              = element_text(colour = ink),
      axis.line         = element_line(linewidth = axis_linewidth, colour = ink),
      axis.ticks        = element_line(linewidth = axis_linewidth, colour = ink),
      axis.ticks.length = unit(2, "pt"),
      axis.text         = element_text(size = tick_size, colour = ink),
      axis.title        = element_text(size = base_size, colour = ink),
      axis.title.x      = element_text(margin = margin(t = 3)),
      strip.background  = element_blank(),
      strip.text        = element_text(size = tick_size, colour = ink),
      panel.spacing     = unit(3, "pt"),
      legend.position   = "none",
      legend.text       = element_text(size = tick_size, colour = ink),
      legend.key.size   = unit(8, "pt"),
      plot.tag          = element_text(size = base_size, face = "bold"),
      plot.margin       = margin(2, 5, 2, 2)
    )
}

# Strategy names as left-hand row strips (used with facet_grid(switch = "y")).
theme_strategy_strips <- function() {
  theme(
    strip.placement   = "outside",
    strip.text.y.left = element_text(angle = 0, hjust = 1, size = tick_size, colour = ink,
                                     margin = margin(r = 4)),
    panel.spacing.y   = unit(5, "pt")
  )
}

# ---- Export -------------------------------------------------------------------
# Writes <name>.pdf (vector, fonts embedded via cairo), .svg (text kept as text),
# .png (600 dpi) and .csv (exactly the data frame the plot was drawn from).
save_figure <- function(plot, name, width, height, data) {
  dir.create(fig_dir, showWarnings = FALSE, recursive = TRUE)
  out <- file.path(fig_dir, name)
  ggsave(paste0(out, ".pdf"), plot, width = width, height = height, units = "in", device = cairo_pdf)
  ggsave(paste0(out, ".svg"), plot, width = width, height = height, units = "in", device = svglite::svglite)
  ggsave(paste0(out, ".png"), plot, width = width, height = height, units = "in", dpi = 600,
         device = "png", type = "cairo")
  write.csv(data, paste0(out, ".csv"), row.names = FALSE)
  message("wrote ", name, " (", width, " x ", height, " in)")
}
