# Real-source collection and harmonization

The V2 pipeline uses original public CDC/NHANES files only. Original measurements and
recruitment were performed by NHANES; this project independently retrieves those files
and performs secondary analysis. No simulated records enter V2 outputs.

## Reproduce collection

```powershell
.\.venv\Scripts\python.exe -c "from study_workbench.research_data import prepare_research; print(prepare_research())"
.\.venv\Scripts\python.exe -c "from study_workbench.research_data import prepare_research; print(prepare_research(offline=True))"
.\.venv\Scripts\python.exe -m pytest tests/test_research_data.py -q
```

`prepare_research(cache_dir='data/research/raw', work_dir='data/research',
output_dir='reports/research', offline=False)` returns absolute paths for the analytic
CSV, source manifest, exclusion flow, quality audit and harmonization table. There is
no network activity on import. Offline mode never attempts a download; missing or
invalid cache files cause a clear failure. An invalid cache is not silently replaced.

The full analytic file is local and ignored by Git. Tracked reports contain aggregates,
metadata and source provenance. Cached XPT bytes remain unchanged. SHA-256 verifies
integrity and repeatability; it is not a separate digital signature from CDC.

## Source inventory

All data URLs follow the official format
`https://wwwn.cdc.gov/Nchs/Data/Nhanes/Public/{year}/DataFiles/{name}.xpt`.
The manifest records every complete URL and its adjacent `.htm` codebook link.

| Period | Year directory | Cycle code | DEMO / SMQ / SMQRTU / SMQFAM / COT records |
| --- | ---: | ---: | --- |
| I, 2015–2016 | 2015 | 9 | 9,971 / 7,001 / 6,744 / 9,971 / 8,608 |
| P, 2017–March 2020 | 2017 | 66 | 15,560 / 11,137 / 10,409 / 15,560 / 13,027 |
| L, August 2021–August 2023 | 2021 | 12 | 11,933 / 9,015 / 7,199 / 11,933 / 8,493 |

I files use suffix `_I`, L files use `_L`, and P files use prefix `P_`. Two additional
L files, HEPA_L and HEPB_S_L, contain 8,611 rows each and supply/independently verify
the phlebotomy weight. Only SEQN and WTPH2YR are selected from them; hepatitis results
are neither selected nor analyzed. The source inventory therefore contains **17 files**.

These are three non-overlapping samples. The overlapping 2017–2018 `_J` release is
never added to P. Source membership is allowlisted; demographic release codes and
cross-period key disjointness are checked. Every within-period source key must match
DEMO; duplicates, missing keys and cardinality violations stop preparation.

Source validation checks documented record counts, required numeric fields, finite
values, valid categorical codes, age/income limits, and cotinine/detection-flag pairing.
A valid XPORT signature plus successful parsing is required; HTML and truncated files
cannot become successful downloads. New source revisions that change record counts
require review rather than silent acceptance.

## Full survey population and weights

The analytic CSV contains **all 37,464 demographic records**. It retains unexamined
people, children, missing questionnaires and unavailable assays. R constructs a
positive-weight survey design before selecting any analytic domain.

| Field | I | P | L |
| --- | --- | --- | --- |
| `weight`, for blood-outcome analysis | WTMEC2YR | WTMECPRP | WTPH2YR from HEPA_L |
| `mec_weight`, for examination availability audits | WTMEC2YR | WTMECPRP | WTMEC2YR |
| Survey design | SDMVSTRA + SDMVPSU | Same; PSU values **1–3** are valid | Same; PSU values 1–2 |

P's official PSU range differs from the usual two-PSU pattern; it must not be truncated
to two. See [P_DEMO](https://wwwn.cdc.gov/Nchs/Data/Nhanes/Public/2017/DataFiles/P_DEMO.htm).

[COT_L documentation](https://wwwn.cdc.gov/Nchs/Data/Nhanes/Public/2021/DataFiles/COT_L.htm)
requires WTPH2YR, but that field is absent from the actual COT_L and DEMO_L XPT files.
[HEPA_L](https://wwwn.cdc.gov/Nchs/Data/Nhanes/Public/2021/DataFiles/HEPA_L.htm) officially
publishes the common blood-draw weight. All **8,493 COT_L keys** match it and every
available cotinine result has a positive weight. The complete 8,611-key/weight mapping
is exactly identical in the independent HEPB_S_L file. These checks run every time.

Missing L phlebotomy weights outside the weight population are retained as **NA**,
never replaced with a generic MEC weight or zero. The actual 3,322 absent mappings
comprise 3,073 people not MEC-examined and 249 examined children under age two.
There are zero available cotinine results without a positive weight. An examined
person aged two or older with an unexplained missing weight causes a failure.

## Canonical coding

`harmonization.csv` gives the period-specific field mapping. Original questionnaire
codes and file-row indicators are also retained to make derivations inspectable.

- Poverty: observed PIR <1, 1–<2, 2–<4 and >=4; missing is `unknown`. PIR=5 is top-coded.
- Education: codes 1/2 → less than high school; 3 → high school/GED; 4 → some college/AA;
  5 → college+. Codes 7/9 and absent responses remain `unknown`. DMDEDUC2 starts at age20.
- Recorded sex: RIAGENDR 1/2 → male/female; absent → unknown.
- Race/Hispanic origin: RIDRETH3 1/2 → Hispanic; 3/4/6 → non-Hispanic white/black/Asian;
  7 → other/multiracial; absent → unknown. Categories describe released survey variables.
- Noncurrent cigarettes: SMQ020=2 with expected skipped SMQ040, or SMQ020=1 & SMQ040=3,
  maps to 1; SMQ020=1 & SMQ040=1/2 maps to 0; unresolved/refused/unknown maps to NA.
- Recent all-product nonuse: require explicit SMQ681=2, SMQ851=2 and SMQ863=2. I/P
  SMQ690H=8 overrides broad nonuse. L additionally requires **SMQ846=2**; a blank,
  refusal or unknown never supplies a no response. A skipped multi-select alone is
  not evidence of nonuse. Any positively reported product use maps to 0 even if
  another use screen is unknown; unresolved nonuse maps to NA.
- Household smoker and indoor household smoking are separate constructs. SMD460=0
  plus structurally skipped SMD470 supplies no resident indoor smoker. Otherwise
  SMD470=0 versus a valid positive value supplies no/yes. Unavailable or special
  responses stay unknown. I uses a 3+ top-code, P/L use 2+; any/none is comparable.

These definitions describe current-cigarette responses and five-day product use.
They do not establish 30-day abstinence. L recent-use interviews also changed from
interviewer CAPI to self-administered ACASI in English/Spanish without proxies, so
period differences may reflect reporting and selection as well as exposure.

## Conservative quality clarifications, before outcome fits

These resolve contradictory or malformed records rather than choosing a result:

1. A nonmissing SMQ040 after a SMQ020 skip prerequisite is a conflict and supplies
   unknown noncurrent status. This conservatively qualifies the plan's abbreviated
   `SMQ020=2` rule. The actual total and age25+ affected counts are **zero in I/P/L**.
2. Positive cigarette `SMQ690A=1` or NRT `SMQ690F=6` excludes recent nonuse despite a
   contradictory broad no; I/P e-cigarette `SMQ690H=8` also overrides it as planned.
   Unknown detail responses following an incompatible broad no are flagged and do
   not supply known nonuse. Actual broad/detail conflicts are **zero in I/P/L**.
3. SMD460=0 with an incompatible nonzero SMD470, or definite indoor counts exceeding
   resident-smoker counts, flags a conflict; derived household fields become unknown.
   Actual total and age25+ household conflict counts are **zero in I/P/L**.

L has 143 people aged25+ reporting e-cigarette use despite no use in the three other
screens. This is an expected separate-screen pattern, not a contradiction; they are
excluded by the frozen SMQ846 rule. The quality audit separately records summary-variable
disagreements, raw skip conflicts and all unknowns. Unknown counts on the full DEMO base
include people outside questionnaire eligibility; they are not automatically data errors.

## Laboratory handling and decoder behavior

Original LBXCOT values and LBDCOTLC flags are retained. LLOD is .015 ng/mL in I/P and
.010 in L. CDC supplies LLOD/sqrt(2) rounded fills below detection (.011 and .007,
respectively); they are kept with their flags. A genuinely absent assay stays absent.
I's valid flag2 denotes an above-calibration detectable result; it maps to not-below-LOD
with the original code retained. The current I file has no flag2 observations.

The common .05 research endpoint is estimated later by R, not this data preparation
module. Native LOD differences therefore cannot change the primary cutoff, but matter
for explicitly declared lower-threshold sensitivities.

Installed pandas can decode exact zero IBM XPORT bytes as `2**-260`
([upstream issue](https://github.com/pandas-dev/pandas/issues/30051)). Only that exact
magnitude in selected numeric fields is normalized to zero. Per-field counts are
manifested, original bytes remain unchanged, and genuine small concentrations are
never broadly rounded to zero.

## Audit outputs and actual flow

The manifest preserves original retrieval time on offline repeats and records a new
verification time, SHA-256, byte/record counts, selected columns, original plan commit,
current plan-file hash, software versions and analytic-CSV hash. Quality outputs contain
no endpoint comparisons. Exclusion flow is cumulative and unweighted, showing which
additional records are lost at each specified step.

| Stage | I | P | L |
| --- | ---: | ---: | ---: |
| All demographic records exported | 9,971 | 15,560 | 11,933 |
| Positive blood-analysis weight | 9,544 | 14,300 | 7,583 |
| Age25+ | 5,053 | 7,912 | 5,518 |
| Noncurrent cigarette response | 4,091 | 6,450 | 4,678 |
| Explicit recent all-product nonuse | 3,446 | 5,584 | 3,711 |
| Available cotinine | 3,290 | 5,262 | 3,562 |
| Cotinine <=10 ng/mL | 3,239 | 5,122 | 3,489 |
| Also observed income | 2,909 | 4,476 | 3,060 |

These are sample-flow counts, not weighted prevalence, event counts, hypothesis tests
or causal findings. Survey estimates and complete-case model accounting are produced
by the independently tested R analysis stage under the frozen plan.
