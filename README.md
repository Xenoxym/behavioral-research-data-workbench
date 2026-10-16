# Tobacco Exposure Equity Study

An independent, reproducible study of income differences in nicotine exposure using
**real CDC NHANES data**. The project combines biological measurement, behavioral
questionnaires, complex-survey statistics and a research data-quality audit.

The analysis plan was committed before comparative outcomes were calculated. All study
observations come from CDC; no synthetic participants enter the research results.
AI assists research planning and software development; inspectable Python/R code
calculates the findings. There is no LLM-based outcome generation or prediction API.

Read the [research report](reports/RESEARCH_REPORT.md) or its
[standalone illustrated HTML](reports/RESEARCH_REPORT.html).
The [final project and job-application report](reports/FINAL_PROJECT_REPORT.md) explains
the completed evidence, resume wording, interview discussion and remaining experience gaps.

## What was investigated

Three non-overlapping samples: **2015–2016**, **2017–March2020**, **August2021–August2023**.
Seventeen original files yield **37,464 demographic records**, retained for complete
survey-design construction; **11,850 records** meet the primary analytic definition.

The question is whether income inequalities in a cotinine exposure indicator persist,
how they relate to indoor household smoking, and how measurement/selection decisions
affect interpretation. This extends established research with a harmonized analysis of
newly released data; it does not claim discovery of socioeconomic inequalities.

- Primary weighted exposure: **19.6%**, **18.1%**, **13.7%** in the defined25+ domains.
- Below-poverty minus ≥400%-of-poverty differences: **22.5**, **26.8**, **27.6 percentage points**.
  All three intervals exclude zero; all crossperiod gap-change intervals include zero.
  The study cannot conclude that inequality widened.
- A measurement audit finds **47.5% native detectability versus36.7% at a common0.015ng/mL
  threshold** in the latest period. Those are different endpoints from the primary0.05
  indicator. Directly comparing native detection rates obscures the assay-limit change.
- Matched-sample regression, twelve scenarios per period and two explicit laboratory
  missingness denominators make assumptions visible. Full estimates and uncertainty are
  retained, including null and boundary results.

See the report for95% intervals, sample counts, formulas and limitations. Observational
period differences are not treatment effects or causal pandemic effects.

## Run the saved research app

Python3.12 and [uv](https://docs.astral.sh/uv/) are recommended. No hardware, GPU,
paid service, API key, Docker or participant recruitment is required.

```powershell
uv sync --frozen
uv run streamlit run app.py --server.address 127.0.0.1 --browser.gatherUsageStats false
```

Open **http://localhost:8501**, or use `start_workbench.cmd` on Windows. The default
app reads committed aggregate results and never downloads automatically. Six pages
cover questions/methods, weighted results, selection/sensitivity, provenance and reports.
All individual-level CDC records remain in ignored local files.

## Reproduce the entire study

On Windows `scripts/setup.ps1` installs project dependencies, prepares an isolated
R runtime, collects official data and reproduces the research. Alternatively:

```powershell
uv sync --frozen --extra dev
powershell -ExecutionPolicy Bypass -File scripts/setup_research_r.ps1
uv run research-workbench research
uv run python scripts/verify_research_replay.py
uv run pytest -q --junitxml=artifacts/junit_v2.xml
uv run ruff check .
```

R4.6.1 with survey4.5/jsonlite2.0.0 is the tested statistical engine. On other platforms
install R with `survey` and `jsonlite`; PATH or `RESEARCH_RSCRIPT` can identify Rscript.
The Windows setup verifies the official installer's signature/checksum, uses `.tools/`,
and leaves global PATH unchanged. See [statistical methods](docs/RESEARCH_STATISTICS.md).
Limit BLAS worker threads to1 during concurrent processes on a memory-constrained
machine (`OPENBLAS_NUM_THREADS=1`, `OMP_NUM_THREADS=1`).

The first `research` command explicitly downloads seventeen official XPT sources.
`research --offline` requires their validated local cache; corrupt or missing entries
cause an error. Replay verification compares all five scientific CSVs byte for byte
and verifies canonical input, source checksums and original retrieval times.
No downloaded measurements are committed. `research --prepare-only` performs only
acquisition, joins, harmonization and quality accounting.

For real Chromium acceptance:

```powershell
uv run playwright install chromium
uv run python scripts/research_browser_smoke.py
```

CI checks Python and R reference calculations on Windows/Ubuntu. A separate manual
**Reproduce real CDC research** workflow downloads and reruns the whole study, then
checks its offline replay. No credentials or paid APIs are used in these workflows.

## Research decisions that matter

1. **Inspect original files as well as codebooks.** COT_L requires WTPH2YR but omits its
   actual column. Recover it through HEPA_L and independently verify every linked weight
   against HEPB_S_L. No hepatitis outcomes are analyzed.
2. **Harmonize questions, not just column names.** Recent e-cigarette use becomes a
   separate question; mode changes from CAPI to ACASI. Unknowns and structural skips
   are separate; 143 latest-period adults aged25+ report e-cigarette use despite all
   three older broad questions indicating nonuse. This is a questionnaire-audit count;
   24 additionally satisfy the noncurrent-cigarette, positive-weight and cotinine≤10 rules.
3. **Respect the survey design.** Construct full positive-weight strata/PSU designs
   before domain subsetting; use period-specific examination/phlebotomy weights and
   joint covariance for income contrasts. Never merge overlapping NHANES releases.
4. **Test interpretations.** Compare M1/M2 on an identical sample, report threshold
   and cohort sensitivity, distinguish missing blood draws from residual missing assays,
   and retain findings that do not support a stronger story.

```text
Official CDC XPT + codebooks → checksum/schema/key validation → full-population harmonization
                                                               ↓
Frozen analysis plan → R survey domains → estimates / contrasts / models / sensitivity
                                                               ↓
                                    static scientific figures + research report + Streamlit
```

## Documentation and provenance

- [Frozen analysis plan and recorded clarifications](docs/RESEARCH_PLAN_V2.md)
- [Source and harmonization methods](docs/RESEARCH_HARMONIZATION.md)
- [Statistical methods and reference validation](docs/RESEARCH_STATISTICS.md)
- [Software contract](docs/RESEARCH_CONTRACT_V2.md)
- [Source manifest](reports/research/source_manifest.json) and [quality audit](reports/research/data_quality.json)
- [Primary/subgroup estimates](reports/research/estimates.csv), [contrasts](reports/research/contrasts.csv), [models](reports/research/models.csv)
- [Sensitivity analyses](reports/research/sensitivities.csv) and [missingness audit](reports/research/missingness.csv)
- [Pipeline hashes](reports/research/pipeline_run.json) and [offline replay evidence](reports/research/replay_validation.json)

The original [V1 workbench](LEGACY_README.md) remains a separate, explicitly synthetic
operations demonstration (`legacy_app.py`). Its contacts/visits are never treated as
actual participant experience or mixed into these cross-sectional results.

This project demonstrates research data management, biosocial measurement, survey
analysis and scientific reporting for research-assistant/public-health/data roles.
It does not establish participant-facing employment, IRB approval, clinical validation,
or the required year of research employment. Published weights do not eliminate all
selection bias. The cohort is CDC-aligned, not an exact replication of its30-day
abstinence criteria; cotinine does not uniquely identify the nicotine source.
