# Scientific analysis sources

`analysis.R` is the inference engine; `reference_validation.R` checks authoritative
survey-package examples. Python validates and harmonizes source data and renders results.
The scientific decisions are in [the frozen plan](../docs/RESEARCH_PLAN_V2.md).

The real study uses no generated participants, imputed synthetic outcome records,
LLM-generated measurements, learned risk score or clinical classifier. AI assistance is
used for research planning, source review and software development. Every numerical
study result is computed from CDC files by deterministic, inspectable analysis code.
Public measurement provenance and conservative interpretation matter more than adding
an AI feature.

The independent reference data are California schools supplied with R survey. Those
reference checks and small software-test fixtures are never included in NHANES results.
Downloaded public NHANES individual-level records stay under ignored `data/research/`;
only source metadata, aggregate estimates, figures and reports are committed.

After setup:

```powershell
uv run research-workbench research
uv run research-workbench research --offline
uv run pytest -q
```

For only file acquisition/harmonization without inference:
`uv run research-workbench research --prepare-only`.

The 2017–March2020 special release overlaps the ordinary 2017–2018 release. This study
uses the special release exclusively for that period; overlapping respondents are never
counted twice. It does not turn independent survey samples into longitudinal follow-up.
