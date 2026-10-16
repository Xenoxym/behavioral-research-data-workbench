# Tobacco Exposure Equity Study — frozen V2 analysis plan

Frozen before comparative outcome analyses on 2026-10-16. This is a timestamped repository
analysis plan, not a registered protocol or a claim of first-in-literature novelty.
Any later changes must be listed under deviations with their reason. Independent public
data collection/secondary analysis; no simulated observations enter research outputs.

## Questions and contribution

1. Among adults aged25+ who report no current cigarette use and no nicotine-product use
   in the preceding5days, how large is the income gradient in a CDC-aligned cotinine
   exposure indicator in 2015–2016, 2017–March2020 and August2021–August2023?
2. How are indoor household smoking and education associated with that indicator, and
   how do income associations change after adjusting for household smoking?
3. How sensitive are estimates to age restriction, the nonsmoker/biomarker definition,
   household nonresponse and laboratory missingness? Do methodological decisions change
   the apparent inequality enough to matter in a research summary?

The contribution is a reproducible, carefully harmonized replication/extension to newly
released data plus a measurement/selection sensitivity audit. Existing studies already
show socioeconomic gradients. We will not claim their discovery or causal pandemic effects.

## Sources (same-period keys only; never duplicate overlapping releases)

Periods I (2015–2016), P (2017–March2020), L (2021–2023) are non-overlapping survey samples.
For each collect DEMO, SMQ, SMQRTU, SMQFAM, COT from official CDC public XPT URLs/codebooks.
L additionally links WTPH2YR from HEPA_L, solely for the public phlebotomy weight. Actual
file verification found COT_L and DEMO_L omit this weight although COT_L documentation
requires it. Feasibility checks showed all COT_L IDs match HEPA_L and weight values agree
with an independent HEPB_S_L file. Preserve this check and its source provenance.

All files require signature, checksum, schema, unique SEQN, same-period match and source
record-count validation. No outcome comparisons informed this plan; only variable
availability, weight coverage and sample feasibility were examined.

Core fields: SEQN, age, recorded sex, race/Hispanic origin, income-to-poverty ratio,
education, strata, PSU, MEC/phlebotomy weights; lifetime/current cigarette responses;
5day smoking/smokeless/NRT use, e-cigarette use; SMD460/SMD470 household smoking;
LBXCOT/LBDCOTLC concentrations and detection flags. Preserve unknown/refused/skip states.

## Harmonized cohort and outcome

Primary age25+; age18+ is a sensitivity without interpreting educational attainment
as completed education. Noncurrent cigarette response: SMQ020=2 or SMQ020=1 & SMQ040=3.
Require explicit SMQ681=2, SMQ851=2 and SMQ863=2. For I/P also exclude any positive
SMQ690H=8 even if the broad screen says no; for L require SMQ846=2 explicitly. This is
not proven30day abstinence and not an exact replication of every CDC nonsmoker criterion.
Do not turn missing multi-select fields into independent evidence of nonuse.

Primary biomarker cohort: observed serum cotinine <=10ng/mL. Indicator exposed=1 when
0.05<=cotinine<=10; exposed=0 below0.05. This follows the range used by CDC DataBrief396
for SHS, but cannot by itself determine the source of nicotine or individual honesty.
Rows >10 are excluded by a specified marker rule, not called confirmed active users.

I/P assay LLOD=.015 and L assay LLOD=.010ng/mL. The common.05 cutoff exceeds both.
Keep published below-LOD fill values/flags; never fill an absent assay with zero.
Secondary thresholds.10 and.015 are explicitly sensitivity analyses; no optimal cutoff
search. Show how the different native LODs would affect a naive detectability comparison.

Poverty groups: ratio<1,1–<2,2–<4,>=4; missing separate in flow and quality audits.
Education: less than high school, high school/GED, some college/AA, college+; unknown
not inferred. Household indoor smoking: SMD460=0 implies no indoor smoker when SMD470
is structurally skipped; otherwise SMD470=0 vs1–3 distinguish none/any, with unknown
separate. Preserve 'household has a smoker' vs 'smokes indoors' as distinct constructs.

## Statistical analysis

Use authoritative R survey functions, called from a reproducible Python data pipeline.
Build the full positive-weight survey design BEFORE domain subsetting: strata SDMVSTRA,
PSU SDMVPSU, nest=TRUE. Period-specific weights: I WTMEC2YR, P WTMECPRP, L WTPH2YR.
Never use generic MEC weights for L blood-outcome estimates. Do not pool periods into
a single artificial continuous panel. The primary results are separate-period estimates.

Report unweighted eligible/event counts, weighted prevalence and95% confidence intervals,
design degrees of freedom and estimate quality warnings. Use svyciprop(method='logit')
for prevalence intervals, with explicit fallback/reporting for zero/all-event cells.
The prespecified primary contrast is the absolute weighted prevalence difference between
poverty<1 and poverty>=4, using joint design covariance (svyby/svycontrast), in each period.
Crossperiod differences in these gaps are secondary and use independent-period variance.

Secondary survey logistic regressions per period: outcome ~ poverty_group + age_decade +
recorded_sex + race_group (M1), then + indoor_smoking (M2). Report OR,95% CI, full model
formula, coefficient/SE, sample loss and convergence. Use quasibinomial, design-based
robust covariance and declared degrees-of-freedom convention. M1 vsM2 attenuation is an
association comparison, NOT a causal mediation analysis. Unstable fits or sparse groups
are flagged and omitted from substantive claims rather than optimized until significant.

Primary contrast and all prespecified secondary results are shown; no p-value-driven
selection. Confidence intervals are uncertainty descriptions; a null result is valid.

## Sensitivity and missingness

- Primary age25+ vs18+; strict all-product exclusion vs cigarette-only screening.
- Common0.05 cutoff vs0.10/.015; alternate upper cotinine cap3 vs10ng/mL.
- Complete income/education/household cases vs explicit unknown categories where sensible;
  explain that missing-category analysis is not an imputation or bias correction.
- Show weighted laboratory availability across income on the full MEC denominator with
  generic MEC weights; separately show residual assay missingness among phlebotomy-weight
  positive L participants. WTPH2YR already adjusts blood nonresponse: do not apply a second
  inverse-probability correction for the same missing blood draws.
- Bound/explain unresolved assay missingness descriptively; do not claim missing-at-random
  or nationally representative complete-case results merely because weights were used.

## Known interpretation limits

Repeated cross-sections support population-period association descriptions, not individual
follow-up or treatment effects. L recent-use interviews changed from interviewer CAPI
to self-administered ACASI (English/Spanish, no proxies), changing potential selection and
reporting. Sampling/collection and laboratory changes also limit temporal attribution.
Income is topcoded; household smoking may be incomplete. Biomarkers reflect recent,
multi-source nicotine exposure. Weighted estimates cannot repair every selection error.

## Outputs and verification

Track source manifest, variable harmonization table, exclusion flow, missingness audit,
analysis code, R/package versions, model/estimate CSVs, prespecified contrasts/sensitivities,
static research figures, manuscript-style report, limitations and actual resume wording.
Main app shows real study results by default; historical synthetic operations run separately.
Validate survey routines on package reference examples; independent implementation review,
sample-flow reconciliation, reproducible offline rerun and end-to-end app/report checks.
Continue committing/pushing milestones; never publish raw confidential or credentials.

## Primary references

- CDC Data Brief396: https://www.cdc.gov/nchs/products/databriefs/db396.htm
- CDC MMWR2018: https://www.cdc.gov/mmwr/volumes/67/wr/mm6748a3.htm
- CDC weighting: https://wwwn.cdc.gov/nchs/nhanes/tutorials/weighting.aspx
- CDC variance/domain guidance: https://wwwn.cdc.gov/nchs/nhanes/tutorials/varianceestimation.aspx
- CDC L cotinine: https://wwwn.cdc.gov/Nchs/Data/Nhanes/Public/2021/DataFiles/COT_L.htm
- R survey svyglm: https://r-survey.r-forge.r-project.org/pkgdown/docs/reference/svyglm.html

## Deviations

None at freezing. Record later changes here before interpreting their results.
