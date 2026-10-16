# Authoritative, offline survey-package examples. No NHANES outcomes are used.
args_all <- commandArgs(trailingOnly = FALSE)
script_arg <- grep("^--file=", args_all, value = TRUE)
root <- if (length(script_arg)) dirname(dirname(normalizePath(sub("^--file=", "", script_arg[1])))) else getwd()
.libPaths(c(file.path(root, ".tools", "R-library"), .libPaths()))
suppressPackageStartupMessages(library(survey))
suppressPackageStartupMessages(library(jsonlite))
options(survey.lonely.psu = "fail")

reference_validation <- function(output_dir) {
  dir.create(output_dir, recursive = TRUE, showWarnings = FALSE)
  data(api, package = "survey", envir = environment())
  stratified <- svydesign(ids = ~1, strata = ~stype, weights = ~pw,
                         fpc = ~fpc, data = apistrat)
  strat_mean <- svymean(~api00, stratified)
  stopifnot(abs(as.numeric(coef(strat_mean)) - 662.28736) < 0.00002)
  stopifnot(abs(as.numeric(SE(strat_mean)) - 9.408941) < 0.00002)

  # A with-replacement cluster example for independent PSU-Taylor validation.
  cluster_input <- data.frame(stratum = 1L, psu = apiclus1$dnum,
                             weight = apiclus1$pw, y = apiclus1$api00,
                             exposed = as.integer(apiclus1$sch.wide == "Yes"),
                             group = as.character(apiclus1$stype))
  cluster <- svydesign(ids = ~psu, strata = ~stratum, weights = ~weight,
                      data = cluster_input, nest = TRUE)
  full <- svymean(~y + exposed, cluster)
  high_school <- subset(cluster, group == "H")
  domain <- svymean(~y + exposed, high_school)
  grouped <- svyby(~exposed, ~group, cluster, svymean, covmat = TRUE)
  names_group <- as.character(grouped$group)
  contrast_vector <- setNames(rep(0, length(names_group)), names_group)
  contrast_vector[c("E", "H")] <- c(1, -1)
  contrast <- svycontrast(grouped, contrast_vector)
  prevalence <- svyciprop(~exposed, cluster, method = "logit", df = degf(cluster))
  result <- list(
    kind = "survey built-in California school API data; not study findings",
    r_version = R.version.string, survey_version = as.character(packageVersion("survey")),
    builtin_stratified = list(mean = as.numeric(coef(strat_mean)), se = as.numeric(SE(strat_mean))),
    full = list(mean = unname(coef(full)), covariance = unname(vcov(full)), df = degf(cluster)),
    domain_H = list(mean = unname(coef(domain)), covariance = unname(vcov(domain)), df = degf(high_school)),
    group_order = names_group, group_estimates = unname(coef(grouped)),
    group_covariance = unname(vcov(grouped)),
    contrast_E_minus_H = list(estimate = as.numeric(coef(contrast)), se = as.numeric(SE(contrast))),
    proportion_logit = list(estimate = as.numeric(coef(prevalence)),
                            interval = as.numeric(confint(prevalence)))
  )
  write.csv(cluster_input, file.path(output_dir, "reference_input.csv"), row.names = FALSE, na = "")
  write_json(result, file.path(output_dir, "reference_results.json"),
             auto_unbox = TRUE, pretty = TRUE, digits = 15, na = "null")
  cat("Built-in survey reference validation passed.\n")
  invisible(result)
}

if (sys.nframe() == 0L) {
  args <- commandArgs(trailingOnly = TRUE)
  reference_validation(if (length(args)) args[1] else file.path(root, "reports", "research", "reference"))
}
