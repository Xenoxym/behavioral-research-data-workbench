# Independent NHANES public-data case

This case uses real CDC public-use survey files. It is separate from the workbench's
synthetic screening and follow-up simulation. It describes adult records in a
cross-sectional sample; it does not evaluate a cessation intervention.

## Sources and reproduction

All three files belong to the **2017-March 2020 pre-pandemic** release. The `P_` prefix
and demographic `SDDSRVYR=66` identify that combined release. Each source is downloaded
only when the public-data command is explicitly run. Opening the application or
importing the module does not contact CDC.

| File | Variables used | Official documentation |
| --- | --- | --- |
| P_DEMO | SEQN, SDDSRVYR, RIDAGEYR, RIDSTATR, WTMECPRP, SDMVSTRA, SDMVPSU | [CDC demographic codebook](https://wwwn.cdc.gov/Nchs/Data/Nhanes/Public/2017/DataFiles/P_DEMO.htm) |
| P_SMQ | SEQN, SMQ020, SMQ040 | [CDC cigarette-use codebook](https://wwwn.cdc.gov/Nchs/Data/Nhanes/Public/2017/DataFiles/P_SMQ.htm) |
| P_COT | SEQN, LBXCOT, LBDCOTLC | [CDC serum-cotinine codebook](https://wwwn.cdc.gov/Nchs/Data/Nhanes/Public/2017/DataFiles/P_COT.htm) |

From the repository root, after installing the project dependencies:

```powershell
.\.venv\Scripts\python.exe -c "from study_workbench.nhanes import run_analysis; run_analysis('reports/nhanes', 'data/nhanes/raw')"
.\.venv\Scripts\python.exe -m pytest tests/test_nhanes.py -q
```

`run_analysis(output_dir, cache_dir=None)` returns a dictionary with `summary`, `paths`
and `provenance`. The default raw cache is `data/nhanes/raw`. It writes these aggregates:

- `summary.json`: sample flow, available/missing counts, groups, mappings and limitations.
- `sample_summary.csv`: group counts and available-result cotinine quantiles.
- `report.html`: standalone report, with visible sample-only interpretation limits.
- `provenance_manifest.json`: source URLs, codebook links, SHA-256 checksums, byte and
  record counts, original retrieval time, verification time and cache status.

Raw XPT files and adjacent cache metadata remain in ignored `data/`; no participant-level
public data are committed. Reusing a verified cache works offline and preserves the
original retrieval timestamp. Source files are a little over 5 MiB in total.

## Validation and joins

Before caching or analysis, the downloader checks the SAS XPORT signature and 80-byte
record layout, then parses the file with pandas. An HTML error response cannot become
a successful data download. Required fields, numeric types, finite values, positive
integer unique SEQN keys and valid category codes are checked.

Cached files require matching source URL, release, byte count, checksum and a timezone-aware
retrieval timestamp. Invalid cache data fail visibly instead of silently being reused
or replaced. To recover, move or delete the named XPT and its `.xpt.json` metadata and rerun.

SMQ and cotinine source keys must exist in the same demographic release. Two validated
one-to-one left joins on SEQN retain every adult demographic record, including records
without questionnaire or laboratory data. An absent laboratory-file row is distinct
from a file row whose laboratory result is missing. Neither is filled as zero.

The installed pandas 2.3.3 decoder produced the documented XPORT artifact `2**-260`
for some true zero values, including infant ages, zero examination weights and the
at/above-LOD flag. The parser normalizes **only that exact magnitude** in selected
numeric fields to zero, records per-column counts in the manifest, and leaves the
original bytes unchanged. It does not round general small measurements. See the
[pandas issue](https://github.com/pandas-dev/pandas/issues/30051).

## Sample and questionnaire coding

The adult base is `RIDAGEYR >= 18`, using age at screening. Age 80 represents 80 years
and older in this public release. No age above the public top-code is inferred.

| Raw responses | Group used here |
| --- | --- |
| SMQ020=2 and SMQ040 missing | Fewer than 100 lifetime cigarettes |
| SMQ020=1 and SMQ040=3 | At least 100 lifetime; now not at all |
| SMQ020=1 and SMQ040=1 | At least 100 lifetime; now every day |
| SMQ020=1 and SMQ040=2 | At least 100 lifetime; now some days |
| SMQ020 or required SMQ040=7 | Refused, separate from ordinary missingness |
| SMQ020 or required SMQ040=9 | Do not know, separate from refused |
| Missing prerequisite or required follow-up | Classification unavailable |
| SMQ040 answered despite a skip prerequisite | Inconsistent skip; not forced into a smoking category |

SMQ040 is an expected skip after SMQ020=2, 7 or 9. A blank SMQ040 alone is therefore
not evidence of a missing required answer. The less-than-100 lifetime category is
not named "no nicotine exposure" and does not establish that a person never used a
cigarette recently. The paired analyzed sample requires one of the first four
classifiable groups and an available serum-cotinine result.

## Laboratory handling and interpretation

`LBXCOT` is serum cotinine in ng/mL. `LBDCOTLC=0` denotes at or above the lower detection
limit; `1` denotes below it. CDC gives the LLOD as **0.015 ng/mL** and substitutes
LLOD/sqrt(2) below it; the published XPT result is rounded to 0.011 ng/mL. The parser
checks the result/flag pairing and allows this published rounding. It preserves the
fill values and counts flags separately. It never substitutes a genuine missing result.

Group medians, 25th and 75th percentiles use all available published concentrations,
including below-LOD fill values. Quantiles near that limit describe a censored
distribution; they should not be interpreted as exact measured low concentrations.

Cotinine is a nicotine-exposure marker. Nicotine replacement, electronic nicotine
products, other nicotine sources, secondhand exposure and timing may affect results.
Those explanations are not resolved by these three files. No concentration cutoff,
diagnosis, abstinence-verification label or judgment about response honesty is assigned.
The [SRNT biochemical-verification review](https://pmc.ncbi.nlm.nih.gov/articles/PMC7882145/)
provides additional context for interpreting nicotine biomarkers.

## Actual run recorded on 2026-10-16

The downloaded files contained 15,560 demographic, 11,137 smoking-questionnaire and
13,027 cotinine records. The adult base contained **9,693** records. All had an adult
questionnaire row; **9,688** had classifiable cigarette responses. Of 8,965 adults
with a cotinine-file row, 8,328 had a result. Total adult cotinine missingness, including
absent laboratory-file rows, was **1,365/9,693**. The paired sample contained **8,324**.

| Cigarette category | Adult records | Cotinine results | Missing cotinine | Median ng/mL |
| --- | ---: | ---: | ---: | ---: |
| Fewer than 100 lifetime | 5,799 | 4,961 | 838 | 0.020 |
| At least 100 lifetime; now not at all | 2,205 | 1,915 | 290 | 0.028 |
| At least 100 lifetime; now every day | 1,306 | 1,118 | 188 | 250.500 |
| At least 100 lifetime; now some days | 378 | 330 | 48 | 92.350 |

Two adults refused SMQ020 and three answered do not know. Their records remain visible
as separate groups; they do not enter the classifiable paired sample. All 5,804 missing
adult SMQ040 answers followed the expected skip. Among all adults with results,
2,759 carried the below-LOD flag. These are **unweighted sample counts**, not population
prevalence or clinical validation results. Exact hashes and retrieval times are in the manifest.

## Statistical limits and testing

No survey weights, design-based standard errors, confidence intervals or hypothesis tests
are computed. WTMECPRP, SDMVSTRA and SDMVPSU are retained to document the source design,
not to imply weighted analysis. A national analysis would require the appropriate combined
release examination weights and survey design, plus evaluation of laboratory nonresponse.
The incomplete 2019-March 2020 component must not be treated as a standalone representative cycle.

The offline unit tests cover adult denominators, skipped/refused/unknown responses,
missing laboratory results, LOD rules, duplicate/missing/foreign join keys, wrong release,
HTML/truncated downloads, cache tampering, original retrieval timestamps, decoder-zero
normalization, and independent labeled aggregate exports. Test download decoding is mocked;
the recorded real-data run separately verifies parsing and analysis of the actual CDC files.

This work demonstrates public research-data ingestion, source traceability and cautious
descriptive reporting. It does not establish clinical experience, participant-contact
experience, or validated health outcomes.
