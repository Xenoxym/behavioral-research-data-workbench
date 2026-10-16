# Survey inference, runtime and independent validation

This document describes the frozen V2 plan's statistics implementation. The real
study is a repeated cross-sectional public-data analysis. No synthetic study
records, language-model predictions or artificial test fixtures enter its results.
See [RESEARCH_PLAN_V2.md](RESEARCH_PLAN_V2.md) for questions, definitions and scope.

## Authoritative engine

`research/analysis.R <harmonized.csv> <output-directory>` uses the CRAN **survey**
package for Taylor-linearized variance, domain estimates, joint covariance,
contrasts and survey-weighted logistic regression. Python prepares the data,
calls this script and creates the report; it does not substitute ordinary weighted
regression or unclustered binomial intervals for complex-survey inference.

The verified local runtime is R4.6.1 (2026-06-24), survey4.5, jsonlite2.0.0. Outputs
record actual versions. R package changes require rerunning reference validation.

On Windows, run from the project root:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/setup_research_r.ps1
$env:LC_ALL='C'
$env:LANG='C'
$env:R_LIBS_USER=(Join-Path (Get-Location).Path '.tools/R-library')
& '.\.tools\R\bin\Rscript.exe' --vanilla research/reference_validation.R reports/research/reference
& '.\.tools\R\bin\Rscript.exe' --vanilla research/analysis.R data/research/analytic.csv reports/research
```

The setup script downloads the official R4.6.1 Windows installer, requires a Valid
Authenticode signature, and compares its MD5 to CRAN's published file fingerprint.
The verified installer SHA256 was
`c5424c40cd70ef85765a55d2ff96bb602b5f30ed536938ff004f14db5db3c2df`.
Its published MD5 was `7907f3a20ec8ec88cd0da279024b8e27`; signer was Martyn Plummer
with a valid Sectigo certificate. The script records installation provenance in
ignored `.tools/R-installation.json` and installs CRAN Windows binary packages in
`.tools/R-library`. It uses current-user, hidden installation with no optional
tasks or shortcuts and no global PATH changes. The runtime stays in `.tools/R`.

On other platforms, install R and `install.packages(c('survey','jsonlite'))` using
CRAN. Tests discover `RESEARCH_RSCRIPT`, then project-local R, then `Rscript` on
PATH. The Python caller sets C locale in its child process to avoid Windows
`C.UTF-8` locale warnings. Binary packages avoid an Rtools/compiler requirement on
Windows. `.tools` and raw data are excluded from Git.

## Survey design and domains

For each period independently, construct the full positive-analysis-weight design
using `svydesign(ids=~psu, strata=~stratum, weights=~analysis_weight, nest=TRUE)`.
Use I `WTMEC2YR`, P `WTMECPRP`, and L `WTPH2YR`. No two-PSU assumption is built in:
the P release contains legitimate PSU codes1–3. Age, product-use, measured-cotinine
and subgroup restrictions are applied **after** design construction using survey
domain subsetting; original design information remains available to the package.

Full DEMO rows include zero-weight nonexamined people. L also has absent blood
weights on non-MEC participants and ages0/1, outside the source weight file's
eligibility. These missing values remain missing and are excluded from the
positive-weight design; they are never replaced by generic MEC weights. Missing
weights on examined age2+ people or any observed cotinine record are rejected.

Period/SEQN pairs must be unique. Numeric values, category codes, positive-weight
design identifiers, age topcoding and weight missingness are validated before
analysis. No period is pooled into a fabricated longitudinal panel.

## Outcomes and estimates

Primary domain: age25+, harmonized noncurrent cigarette response, explicit no
recent all-product use, and observed cotinine<=10ng/mL. The outcome is1 for
cotinine>=0.05ng/mL and0 below that value. The operational phenotype cannot prove
30day abstinence, exposure source or clinical smoking status.

Prevalence is computed with `svymean`, with its design-based standard error.
Intervals use `svyciprop(method='logit', df=degf(domain_design))`. Point estimates
and all intervals are proportions0–1, not percentages. Domain design degrees of
freedom are reported; they need not equal those of the full design. Zero/all-event
domains retain their observed point estimate and receive `boundary_no_ci`, with
no invented confidence interval. Empty domains are retained with `no_data`.

Diagnostic flags cover n<30, domain design df<8 and fewer than5 events or
non-events. These are explicit cautions, **not certification that the full NCHS
data presentation standards were implemented**. Naive Wald intervals and normal
1.96 critical values are not used as the default proportion method.

The primary contrast is poverty<1 minus poverty>=4 in each period. `svyby(...,
covmat=TRUE)` and `svycontrast` retain their joint covariance. Treating two income
groups in the same sample as independent would generally give the wrong SE.
The contrast uses a t interval with the low/high domain design df. Additional
crossperiod changes in the gap use the independent-period variance sum and
Satterthwaite df; they are secondary, not evidence of pandemic causation.

## Regression

M1 formula is `exposed ~ poverty_group + age_decade + sex + race_group`; M2 adds
`indoor_smoking`. Reference levels are income>=4, female, non-Hispanic White,
and no indoor smoking. Age is age-at-screening divided by10. Models are
`svyglm(..., family=quasibinomial())`, with design-robust covariance.

Reported terms contain log-odds coefficients, SEs, odds ratios and intervals on
the odds-ratio scale. Intervals/tests use the declared domain design df rather
than a normal approximation or automatically selected model-residual df.
Odds ratios are associations, not risk ratios, causal effects or predictions.

`M1_all` uses all primary-domain records with complete income, sex, race and age.
`M1_common` further requires known indoor smoking; `M2` uses **exactly that same
sample**. Only M1_common versus M2 is appropriate for describing association
attenuation after household adjustment. Comparing M1_all with M2 would also mix
in a change of sample. This clarification was recorded before fitting.

The metadata retain sample loss, complete formulas, convergence, fit warnings and
errors. Small model samples, nonconvergence and extreme/nonfinite coefficients
are flagged. Failed fits produce explicit rows instead of disappearing. Flagged
unstable models must not be used as substantive evidence. Household adjustment
does not establish mediation: it may condition on part of a social pathway.

## Missingness and sensitivity

`missingness.csv` reports cotinine absence among all age25+ MEC-examined adults,
with generic MEC weights and income groups including unknown. L additionally
reports residual assay missingness among positive-phlebotomy-weight adults.
WTPH2YR already adjusts blood nonresponse; a second correction for the same
missing blood draws would double-adjust it. The analysis does not do that.

Prespecified scenario IDs in `sensitivities.csv` are:

- `primary`, `age18`, `cigarette_only`;
- `cutoff_0_10`, `cutoff_0_015`, `naive_native_detectability`;
- `upper_cap3`, `household_complete`, `income_complete`, `education_complete`;
- `lab_missing_unexposed`, `lab_missing_exposed`.

The cigarette-only scenario uses noncurrent cigarette responses without the
all-product restriction; it is explicitly a different, less restrictive cohort.
Unknown categories in descriptive tables and complete-case restrictions are not
imputation or correction for selection bias.

The common0.015 threshold is a sensitivity endpoint; native detectability uses
numeric concentration>=the native LOD (.015 I/P; .010 L). The latter illustrates
an unharmonized comparison, not a valid uniform exposure endpoint. LOD comment
flags remain in source/harmonization audits; published fill values are preserved.
Neither missing assay values nor below-LOD measurements are replaced with zero
in the observed-data analysis.

For the two missing-assay extremes, unresolved assay records in the self-reported
eligible domain are assumed biomarker-eligible and assigned either unexposed or
exposed. These are descriptive sensitivity bounds, not a missing-at-random model.
Their prevalence SE/CI and gap SE/CI are deliberately absent, with the flag
`descriptive_bound_no_ci`; sampling uncertainty conditional on a made-up missing
outcome must not look like uncertainty about the missingness assumption itself.
The gap of each scenario is shown, but those two scenario gaps are not guaranteed
sharp lower/upper bounds on an inequality contrast. Additional unmeasured
selection into questionnaires is not resolved by these assay scenarios.

## Outputs and verification

The engine writes `estimates.csv`, `contrasts.csv`, `models.csv`,
`sensitivities.csv`, `missingness.csv`, and `analysis_metadata.json`. The latter
contains input checksum, actual engine versions, formulas, weight identities,
sample counts, df conventions, warnings and limitations. The Python workflow
adds official-source SHA256 provenance and the manuscript-style report.

`research/reference_validation.R` runs the survey package's documented API
examples, independent of NHANES outcomes. The stratified built-in example gives
api00 mean662.2873631593208 and SE9.40894080278458. It also exports a clustered
example, an H-school domain, group covariance and an E-minus-H contrast.

`tests/test_research_statistics.py` independently reconstructs with-replacement
PSU-Taylor covariance in NumPy for the full sample, domain and joint contrasts,
matching the R reference to tight tolerances. This calculation is test-only;
the product's inference remains in R. Artificial schema/sensitivity fixtures
stay in temporary test directories and never become research results.

Run `python -m pytest tests/test_research_statistics.py -q`. Tests skip explicitly
if R is absent; a release must actually execute them with R survey installed.
Passing these checks establishes implementation consistency, not clinical
validation, absence of all bias, or general validity of the epidemiologic model.

## Primary technical sources

- [CDC variance/domain guidance](https://wwwn.cdc.gov/nchs/NHANES/tutorials/VarianceEstimation.aspx)
- [CDC weighting guidance](https://wwwn.cdc.gov/nchs/nhanes/tutorials/weighting.aspx)
- [NCHS proportion presentation standards](https://www.cdc.gov/nchs/data/series/sr_02/sr02_175.pdf)
- [COT_L weight, missingness and detection-limit documentation](https://wwwn.cdc.gov/Nchs/Data/Nhanes/Public/2021/DataFiles/COT_L.htm)
- [R survey reference manual](https://cran.r-project.org/web/packages/survey/survey.pdf)
- [Official R Windows installation FAQ](https://cran.r-project.org/bin/windows/base/rw-FAQ.html)
