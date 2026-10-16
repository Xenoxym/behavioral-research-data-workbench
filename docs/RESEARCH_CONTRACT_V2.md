# V2 integration contract

The scientific specification is [the frozen analysis plan](RESEARCH_PLAN_V2.md).
This file records software interfaces, not additional research hypotheses.

## Pipeline

`research-workbench research` calls `prepare_research` to validate official CDC files,
harmonize the full demographic population, and write `data/research/analytic.csv`.
`--offline` prohibits network access and requires validated cached sources. Raw files
and individual-level records stay outside Git. Public aggregate results and source
checksums are committed.

The R engine is `Rscript --vanilla research/analysis.R <analytic.csv> <output-dir>`.
It uses the full positive-weight design before domain selection. Python never silently
replaces failed survey inference with an unweighted or independent-observation method.
R can be selected with `--rscript` / `RESEARCH_RSCRIPT`, or discovered in project-local
`.tools/R/bin` or PATH. Its library is `.tools/R-library` when present. Locale variables
are set only on the child process.

## Canonical data

One row per same-period SEQN, including people outside the eventual analytic domain.
Fields: period I/P/L; period_label; SEQN; stratum; psu; weight (period-appropriate blood
analysis weight); mec_weight; age; sex; race_group; income_ratio; poverty_group;
education; indoor_smoking; household_smoker; noncurrent; no_recent_all; cotinine;
below_lod; lod. Additional raw question/presence flags support audit. Blank numeric flags
mean unknown, not zero. Categories are defined in the harmonization documentation.

## Saved research outputs

Under `reports/research/`:

- Source layer: source_manifest.json, sample_flow.csv, data_quality.json, harmonization.csv.
- Inference: estimates.csv, contrasts.csv, models.csv, sensitivities.csv, missingness.csv,
  analysis_metadata.json, engine.log. Rates/differences are proportions, not percentages.
- Provenance: pipeline_run.json contains input, analysis-code, plan and output SHA256s.
- Figures: static PNG and SVG exports. These are generated using standard plotting tools.
- Reference: R survey built-in data and independent Taylor-variance verification.

`reports/RESEARCH_REPORT.html` is standalone with embedded figures; its Markdown source
is `reports/RESEARCH_REPORT.md`. The final job-application report links this study and
records actual software acceptance results. The default app reads saved real-data outputs;
it never downloads automatically. `legacy_app.py` preserves V1 simulated research operations.

## Acceptance

Check source identity, one-to-one joins, weight recovery against an independent source,
questionnaire skip patterns, all exclusion counts, survey reference results, uncertainty
and matched-sample models. Re-run offline and compare inference output hashes. Exercise
the real-data app in Chromium, inspect report/figure rendering, run local tests and CI.
Do not describe synthetic unit fixtures or reference school data as study observations.
