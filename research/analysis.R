# Authoritative survey inference for the frozen public-data research plan.
# Usage: Rscript --vanilla research/analysis.R <harmonized.csv> <output-directory>
args_all <- commandArgs(trailingOnly = FALSE)
script_arg <- grep("^--file=", args_all, value = TRUE)
project_root <- if (length(script_arg)) dirname(dirname(normalizePath(sub("^--file=", "", script_arg[1])))) else getwd()
.libPaths(c(file.path(project_root, ".tools", "R-library"), .libPaths()))
suppressPackageStartupMessages(library(survey))
suppressPackageStartupMessages(library(jsonlite))
options(survey.lonely.psu = "fail", survey.adjust.domain.lonely = FALSE)

required_columns <- c("period", "period_label", "SEQN", "stratum", "psu", "weight", "mec_weight",
                      "age", "sex", "race_group", "income_ratio", "poverty_group", "education",
                      "indoor_smoking", "household_smoker", "noncurrent", "no_recent_all",
                      "cotinine", "below_lod", "lod")

safe_mask <- function(x) { x[is.na(x)] <- FALSE; x }
collapse_flags <- function(x) paste(unique(x[nzchar(x)]), collapse = ";")

validate_input <- function(frame) {
  if (!all(required_columns %in% names(frame))) stop("Missing harmonized input columns: ", paste(setdiff(required_columns, names(frame)), collapse = ", "))
  if (!nrow(frame)) stop("Harmonized input contains no records")
  if (any(!frame$period %in% c("I", "P", "L"))) stop("Only frozen-plan periods I/P/L are supported")
  if (any(is.na(frame$SEQN)) || anyDuplicated(frame[c("period", "SEQN")])) stop("Missing or duplicate period/SEQN keys")
  for (name in c("stratum", "psu", "weight", "mec_weight", "age", "income_ratio", "noncurrent", "no_recent_all", "cotinine", "below_lod", "lod")) {
    original <- frame[[name]]
    numeric_value <- suppressWarnings(as.numeric(original))
    if (any(!is.na(original) & (is.na(numeric_value) | !is.finite(numeric_value)))) stop("Invalid numeric input in ", name)
    frame[[name]] <- numeric_value
  }
  if (any(frame$weight < 0, na.rm = TRUE) || any(frame$mec_weight < 0, na.rm = TRUE)) stop("Negative survey weight")
  if (any(frame$age < 0 | frame$age > 80, na.rm = TRUE)) stop("Invalid or non-NHANES top-coded age")
  if (any(frame$cotinine < 0, na.rm = TRUE)) stop("Negative cotinine concentration")
  for (name in c("noncurrent", "no_recent_all", "below_lod")) {
    if (any(!is.na(frame[[name]]) & !frame[[name]] %in% c(0, 1))) stop("Invalid binary field ", name)
  }
  category_levels <- list(sex = c("male", "female", "unknown"),
                          race_group = c("hispanic", "nh_white", "nh_black", "nh_asian", "other", "unknown"),
                          poverty_group = c("lt1", "1to2", "2to4", "ge4", "unknown"),
                          education = c("lt_hs", "hs", "some_college", "college", "unknown"),
                          indoor_smoking = c("yes", "no", "unknown"),
                          household_smoker = c("yes", "no", "unknown"))
  for (name in names(category_levels)) {
    if (any(is.na(frame[[name]]) | !frame[[name]] %in% category_levels[[name]])) stop("Invalid harmonized category in ", name)
  }
  if (any(is.na(frame$mec_weight))) stop("Generic MEC weights must be explicit zero or nonnegative values")
  # Full-DEMO L includes interview-only records and ages0/1 outside HEPA weight
  # eligibility. Preserve these missing weights; never substitute generic MEC.
  unexplained_weight_missing <- is.na(frame$weight) &
    !(frame$period == "L" & (frame$mec_weight == 0 | frame$age < 2))
  if (any(safe_mask(unexplained_weight_missing)) || any(is.na(frame$weight) & !is.na(frame$cotinine))) stop("Unexplained missing analysis weight")
  positive <- safe_mask(frame$weight > 0 | frame$mec_weight > 0)
  if (any(is.na(frame$stratum[positive])) || any(is.na(frame$psu[positive]))) stop("Positive-weight records need stratum and PSU")
  frame
}

make_design <- function(frame, weight_column = "weight") {
  # Only weight eligibility is filtered here. Age/product/lab domains come later.
  frame <- frame[safe_mask(frame[[weight_column]] > 0), , drop = FALSE]
  if (!nrow(frame)) stop("No positive-weight design records for ", weight_column)
  frame$analysis_weight <- frame[[weight_column]]
  svydesign(ids = ~psu, strata = ~stratum, weights = ~analysis_weight,
            data = frame, nest = TRUE)
}

cohort_mask <- function(frame, min_age = 25, strict_products = TRUE, upper_cap = 10,
                        include_missing_lab = FALSE, complete_household = FALSE,
                        complete_income = FALSE, complete_education = FALSE) {
  keep <- safe_mask(frame$age >= min_age & frame$noncurrent == 1)
  if (strict_products) keep <- keep & safe_mask(frame$no_recent_all == 1)
  keep <- keep & (safe_mask(!is.na(frame$cotinine) & frame$cotinine <= upper_cap) |
                    (include_missing_lab & is.na(frame$cotinine)))
  if (complete_household) keep <- keep & frame$indoor_smoking != "unknown"
  if (complete_income) keep <- keep & frame$poverty_group != "unknown"
  if (complete_education) keep <- keep & frame$education != "unknown"
  safe_mask(keep)
}

estimate_domain <- function(design, domain, outcome = "exposed") {
  domain <- safe_mask(domain)
  sub <- design[domain, ]
  n <- sum(domain)
  events <- if (n) sum(sub$variables[[outcome]], na.rm = TRUE) else 0L
  empty <- list(n = n, events = events, prevalence = NA_real_, se = NA_real_,
                ci_low = NA_real_, ci_high = NA_real_, df = if (n) degf(sub) else 0,
                quality_flag = "no_data", weighted_denominator = if (n) sum(weights(sub)) else 0)
  if (!n) return(empty)
  statistic <- svymean(reformulate(outcome), sub, na.rm = TRUE)
  p <- as.numeric(coef(statistic)); se <- as.numeric(SE(statistic)); df <- degf(sub)
  flags <- c(if (n < 30) "n_lt30", if (df < 8) "df_lt8",
             if (events < 5 || n - events < 5) "sparse_events")
  ci <- c(NA_real_, NA_real_)
  if (p <= 0 || p >= 1) {
    flags <- c(flags, "boundary_no_ci")
  } else if (df <= 0) {
    flags <- c(flags, "no_design_df")
  } else {
    interval <- tryCatch(suppressWarnings(svyciprop(reformulate(outcome), sub,
                          method = "logit", df = df)), error = function(e) NULL)
    if (!is.null(interval)) ci <- as.numeric(confint(interval))
    if (any(!is.finite(ci))) flags <- c(flags, "ci_unavailable")
  }
  list(n = n, events = events, prevalence = p, se = se,
       ci_low = ci[1], ci_high = ci[2], df = df,
       quality_flag = collapse_flags(flags), weighted_denominator = sum(weights(sub)))
}

poverty_contrast <- function(design, domain) {
  sub <- design[safe_mask(domain & design$variables$poverty_group %in% c("lt1", "ge4")), ]
  empty <- list(estimate = NA_real_, se = NA_real_, ci_low = NA_real_, ci_high = NA_real_,
                df = if (nrow(sub$variables)) degf(sub) else 0, quality_flag = "missing_poverty_group")
  if (!all(c("lt1", "ge4") %in% sub$variables$poverty_group)) return(empty)
  groups <- svyby(~exposed, ~poverty_group, sub, svymean, covmat = TRUE, na.rm = TRUE)
  contrast <- setNames(rep(0, nrow(groups)), as.character(groups$poverty_group))
  contrast[c("lt1", "ge4")] <- c(1, -1)
  result <- svycontrast(groups, contrast)
  point <- as.numeric(coef(result)); se <- as.numeric(SE(result)); df <- degf(sub)
  interval <- if (df > 0) point + c(-1, 1) * qt(.975, df) * se else c(NA_real_, NA_real_)
  list(estimate = point, se = se, ci_low = interval[1], ci_high = interval[2],
       df = df, quality_flag = collapse_flags(c(if (df < 8) "df_lt8",
         if (any(table(droplevels(sub$variables$poverty_group)) < 30)) "group_n_lt30")))
}

model_rows <- function(design, primary_domain, period) {
  vars <- design$variables
  complete_m1 <- safe_mask(primary_domain & vars$poverty_group != "unknown" &
                          vars$sex != "unknown" & vars$race_group != "unknown" & !is.na(vars$age))
  common <- complete_m1 & vars$indoor_smoking != "unknown"
  masks <- list(M1_all = complete_m1, M1_common = common, M2 = common)
  formula_m1 <- exposed ~ poverty_group + age_decade + sex + race_group
  formula_m2 <- update(formula_m1, . ~ . + indoor_smoking)
  rows <- list(); diagnostics <- list()
  for (model_name in names(masks)) {
    sub <- design[masks[[model_name]], ]
    n <- nrow(sub$variables); events <- sum(sub$variables$exposed, na.rm = TRUE)
    df <- if (n) degf(sub) else 0
    formula <- if (model_name == "M2") formula_m2 else formula_m1
    model_warnings <- character(); model_error <- NULL
    fit <- tryCatch(withCallingHandlers(
      svyglm(formula, design = sub, family = quasibinomial(),
             control = glm.control(maxit = 100)),
      warning = function(w) { model_warnings <<- c(model_warnings, conditionMessage(w)); invokeRestart("muffleWarning") }),
      error = function(e) { model_error <<- conditionMessage(e); NULL })
    flags <- c(if (df < 8) "df_lt8", if (n < 100 || events < 20 || n - events < 20) "small_model_sample")
    if (is.null(fit)) {
      flags <- c(flags, "fit_failed")
      rows[[length(rows) + 1L]] <- data.frame(period = period, model = model_name, term = "(fit failed)",
        coefficient = NA_real_, se = NA_real_, odds_ratio = NA_real_, ci_low = NA_real_, ci_high = NA_real_,
        p_value = NA_real_, n = n, events = events, converged = FALSE, df = df,
        quality_flag = collapse_flags(flags))
    } else {
      beta <- coef(fit); se <- sqrt(diag(vcov(fit)))
      if (!isTRUE(fit$converged)) flags <- c(flags, "not_converged")
      if (any(!is.finite(beta)) || any(!is.finite(se)) || any(abs(beta) > 10, na.rm = TRUE)) flags <- c(flags, "unstable_coefficients")
      if (length(model_warnings)) flags <- c(flags, "fit_warning")
      critical <- if (df > 0) qt(.975, df) else NA_real_
      for (term in names(beta)) rows[[length(rows) + 1L]] <- data.frame(
        period = period, model = model_name, term = term, coefficient = unname(beta[term]),
        se = unname(se[term]), odds_ratio = unname(exp(beta[term])),
        ci_low = unname(exp(beta[term] - critical * se[term])),
        ci_high = unname(exp(beta[term] + critical * se[term])),
        p_value = if (df > 0) unname(2 * pt(-abs(beta[term] / se[term]), df)) else NA_real_,
        n = n, events = events, converged = isTRUE(fit$converged), df = df,
        quality_flag = collapse_flags(flags))
    }
    diagnostics[[model_name]] <- list(formula = paste(deparse(formula), collapse = " "),
      n = n, events = events, df = df, n_lost_from_primary = sum(primary_domain) - n,
      converged = !is.null(fit) && isTRUE(fit$converged),
      quality_flag = collapse_flags(flags), warnings = unique(model_warnings), error = model_error)
  }
  list(rows = do.call(rbind, rows), diagnostics = diagnostics)
}

run_analysis <- function(input_path, output_dir) {
  raw <- read.csv(input_path, stringsAsFactors = FALSE, na.strings = c("", "NA"), check.names = FALSE)
  frame <- validate_input(raw)
  dir.create(output_dir, recursive = TRUE, showWarnings = FALSE)
  frame$age_decade <- frame$age / 10
  frame$poverty_group <- factor(frame$poverty_group, levels = c("ge4", "lt1", "1to2", "2to4", "unknown"))
  frame$sex <- factor(frame$sex, levels = c("female", "male", "unknown"))
  frame$race_group <- factor(frame$race_group, levels = c("nh_white", "hispanic", "nh_black", "nh_asian", "other", "unknown"))
  frame$indoor_smoking <- factor(frame$indoor_smoking, levels = c("no", "yes", "unknown"))
  frame$exposed <- as.integer(frame$cotinine >= .05)
  frame$lab_missing <- as.integer(is.na(frame$cotinine))
  estimates <- list(); contrasts <- list(); sensitivities <- list(); missingness <- list(); models <- list(); period_metadata <- list()
  main_contrasts <- list()
  for (period in c("I", "P", "L")) {
    period_frame <- frame[frame$period == period, , drop = FALSE]
    if (!nrow(period_frame)) next
    design <- make_design(period_frame)
    vars <- design$variables
    primary <- cohort_mask(vars)
    group_levels <- list(overall = "all", poverty_group = c("lt1", "1to2", "2to4", "ge4", "unknown"),
                         education = c("lt_hs", "hs", "some_college", "college", "unknown"),
                         indoor_smoking = c("yes", "no", "unknown"))
    for (variable in names(group_levels)) for (group in group_levels[[variable]]) {
      mask <- primary & if (variable == "overall") TRUE else vars[[variable]] == group
      estimates[[length(estimates) + 1L]] <- as.data.frame(c(list(period = period, group_variable = variable, group = group), estimate_domain(design, mask)), stringsAsFactors = FALSE)
    }
    contrast <- poverty_contrast(design, primary)
    main_contrasts[[period]] <- contrast
    contrasts[[length(contrasts) + 1L]] <- as.data.frame(c(list(period = period, contrast = "poverty_lt1_minus_ge4"), contrast), stringsAsFactors = FALSE)
    scenarios <- list(
      primary = list(description = "Age25+, strict all-product exclusion, cotinine<=10, cutoff0.05"),
      age18 = list(min_age = 18, description = "Age18+; education interpreted cautiously"),
      cigarette_only = list(strict_products = FALSE, description = "Noncurrent cigarette response only; no all-product screen"),
      cutoff_0_10 = list(cutoff = .10, description = "Prespecified common cutoff0.10ng/mL"),
      cutoff_0_015 = list(cutoff = .015, description = "Common detectability cutoff0.015ng/mL across different native LODs"),
      naive_native_detectability = list(native_lod = TRUE, description = "Method audit only: native LOD0.015 in I/P versus0.010 in L; not a harmonized endpoint"),
      upper_cap3 = list(upper_cap = 3, description = "Exclude cotinine>3ng/mL; alternate contamination-sensitive cohort"),
      household_complete = list(complete_household = TRUE, description = "Exclude unknown household indoor-smoking responses"),
      income_complete = list(complete_income = TRUE, description = "Exclude unknown income; not an imputation"),
      education_complete = list(complete_education = TRUE, description = "Exclude unknown education; not an imputation"),
      lab_missing_unexposed = list(include_missing_lab = TRUE, fill_missing = 0, description = "Extreme lower missingness scenario: every unresolved assay assigned unexposed and eligible"),
      lab_missing_exposed = list(include_missing_lab = TRUE, fill_missing = 1, description = "Extreme upper missingness scenario: every unresolved assay assigned exposed and eligible")
    )
    for (name in names(scenarios)) {
      spec <- scenarios[[name]]
      scenario_design <- design
      cutoff <- if (is.null(spec$cutoff)) .05 else spec$cutoff
      if (isTRUE(spec$native_lod)) cutoff <- vars$lod
      scenario_design$variables$exposed <- as.integer(vars$cotinine >= cutoff)
      if (!is.null(spec$fill_missing)) scenario_design$variables$exposed[is.na(vars$cotinine)] <- spec$fill_missing
      arguments <- spec[intersect(names(spec), c("min_age", "strict_products", "upper_cap", "include_missing_lab", "complete_household", "complete_income", "complete_education"))]
      mask <- do.call(cohort_mask, c(list(frame = vars), arguments))
      estimate <- estimate_domain(scenario_design, mask)
      gap <- poverty_contrast(scenario_design, mask)
      # These bounds are scenarios, not confidence limits for the missing-data mechanism.
      if (!is.null(spec$fill_missing)) {
        estimate$ci_low <- estimate$ci_high <- NA_real_
        estimate$se <- NA_real_
        estimate$quality_flag <- collapse_flags(c(estimate$quality_flag, "descriptive_bound_no_ci"))
        gap$ci_low <- gap$ci_high <- gap$se <- NA_real_
      }
      sensitivities[[length(sensitivities) + 1L]] <- as.data.frame(c(
        list(period = period, scenario = name), estimate, list(description = spec$description,
          poverty_gap = gap$estimate, poverty_gap_se = gap$se, poverty_gap_ci_low = gap$ci_low,
          poverty_gap_ci_high = gap$ci_high, poverty_gap_df = gap$df)), stringsAsFactors = FALSE)
    }
    mec_design <- make_design(period_frame, "mec_weight")
    designs <- list(all_MEC_adults25 = mec_design)
    if (period == "L") designs$positive_phlebotomy_adults25 <- design
    for (denominator in names(designs)) {
      audit_design <- designs[[denominator]]
      for (group in c("all", "lt1", "1to2", "2to4", "ge4", "unknown")) {
        mask <- safe_mask(audit_design$variables$age >= 25)
        if (group != "all") mask <- mask & audit_design$variables$poverty_group == group
        estimate <- estimate_domain(audit_design, mask, "lab_missing")
        names(estimate)[names(estimate) == "events"] <- "missing_n"
        names(estimate)[names(estimate) == "prevalence"] <- "missing_rate"
        missingness[[length(missingness) + 1L]] <- as.data.frame(c(list(period = period,
          denominator = denominator, group_variable = if (group == "all") "overall" else "poverty_group", group = group), estimate), stringsAsFactors = FALSE)
      }
    }
    fitted_models <- model_rows(design, primary, period)
    models[[period]] <- fitted_models$rows
    period_metadata[[period]] <- list(label = unique(period_frame$period_label),
      weight = if (period == "I") "WTMEC2YR" else if (period == "P") "WTMECPRP" else "WTPH2YR",
      design_records = nrow(vars), design_df = degf(design), primary_n = sum(primary),
      primary_events = sum(vars$exposed[primary]), native_lod = unique(period_frame$lod),
      cotinine_above10_in_selfreported_cohort = sum(safe_mask(vars$age >= 25 & vars$noncurrent == 1 & vars$no_recent_all == 1 & vars$cotinine > 10)),
      model_diagnostics = fitted_models$diagnostics)
  }
  if (!length(estimates)) stop("No estimable period")
  # Secondary differences in independently sampled period gaps; no pandemic attribution.
  for (comparison in list(c("I", "P"), c("P", "L"), c("I", "L"))) {
    earlier <- main_contrasts[[comparison[1]]]; later <- main_contrasts[[comparison[2]]]
    if (is.null(earlier) || is.null(later)) next
    if (!is.finite(earlier$se) || !is.finite(later$se)) {
      contrasts[[length(contrasts) + 1L]] <- data.frame(period = paste(comparison, collapse = "_to_"),
        contrast = "change_in_poverty_gap_later_minus_earlier", estimate = NA_real_, se = NA_real_,
        ci_low = NA_real_, ci_high = NA_real_, df = NA_real_, quality_flag = "not_estimable_period_gap")
      next
    }
    variance <- earlier$se^2 + later$se^2
    df_denominator <- earlier$se^4 / earlier$df + later$se^4 / later$df
    df <- if (df_denominator > 0) variance^2 / df_denominator else NA_real_
    point <- later$estimate - earlier$estimate; se <- sqrt(variance)
    ci <- if (is.finite(df) && df > 0) point + c(-1, 1) * qt(.975, df) * se else c(NA_real_, NA_real_)
    contrasts[[length(contrasts) + 1L]] <- data.frame(period = paste(comparison, collapse = "_to_"),
      contrast = "change_in_poverty_gap_later_minus_earlier", estimate = point, se = se,
      ci_low = ci[1], ci_high = ci[2], df = df, quality_flag = "secondary_independent_periods_satterthwaite")
  }
  output <- list(estimates = do.call(rbind, estimates), contrasts = do.call(rbind, contrasts),
                 models = do.call(rbind, models), sensitivities = do.call(rbind, sensitivities),
                 missingness = do.call(rbind, missingness))
  for (name in names(output)) write.csv(output[[name]], file.path(output_dir, paste0(name, ".csv")), row.names = FALSE, na = "")
  metadata <- list(engine = "R survey authoritative design-based inference", r_version = R.version.string,
    package_versions = list(survey = as.character(packageVersion("survey")), jsonlite = as.character(packageVersion("jsonlite"))),
    generated_at_utc = format(Sys.time(), "%Y-%m-%dT%H:%M:%SZ", tz = "UTC"),
    input_md5 = unname(tools::md5sum(input_path)), analysis_plan = "docs/RESEARCH_PLAN_V2.md",
    prevalence_ci = "survey::svyciprop(method='logit', df=degf(domain_design)); boundary cells have no CI",
    variance = "Taylor linearization; full positive-weight design before domains; original PSU/stratum information retained",
    contrast_ci = "svyby covariance + svycontrast; t df=degf(low/high domain design)",
    crossperiod_ci = "Independent-period variance sum, Satterthwaite df; secondary association comparison",
    model_ci = "Design-robust survey::svyglm quasibinomial; t CI and tests with domain design df (PSUs minus strata), not normal or residual-model df",
    references = list(poverty = "ge4", sex = "female", race_group = "nh_white", indoor_smoking = "no"),
    primary_numerator = "Serum cotinine0.05-10ng/mL", primary_denominator = "Age25+, noncurrent cigarette responses, no5dayallproducts, observed cotinine<=10; protocol phenotype not clinical truth",
    quality_flags = "Diagnostic warnings n<30, design df<8, <5 events/non-events, boundary intervals; NOT a full NCHS presentation-standards certification",
    limitations = c("No causal effects, clinical classification, or novelty guarantee", "Missing-category summaries are not imputation or nonresponse correction", "Laboratory missingness extreme scenarios are not MAR estimates or missing-mechanism confidence intervals", "L phlebotomy weights already adjust blood nonresponse; no second IPW adjustment applied", "Survey-mode, sample-design and laboratory changes limit period comparisons", "Model coefficients flagged unstable must not support substantive claims", "M1_all differs in sample; compare only M1_common with M2 for conditional association changes"),
    periods = period_metadata,
    output_rows = lapply(output, nrow))
  write_json(metadata, file.path(output_dir, "analysis_metadata.json"), auto_unbox = TRUE,
             pretty = TRUE, digits = 15, na = "null", null = "null")
  cat("Survey analysis complete: ", output_dir, "\n", sep = "")
  invisible(output)
}

if (sys.nframe() == 0L) {
  args <- commandArgs(trailingOnly = TRUE)
  if (length(args) != 2L) stop("Usage: Rscript research/analysis.R <harmonized.csv> <output-directory>")
  run_analysis(args[1], args[2])
}
