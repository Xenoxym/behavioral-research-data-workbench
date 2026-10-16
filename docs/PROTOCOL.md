# Synthetic behavioral-study protocol and operating procedure

Version1.0. Reference observation date2026-10-16. This is a software demonstration,
not a protocol for conducting a study with people. No intervention efficacy is simulated.

## Research question and design

Can a research assistant identify data problems, organize due follow-up visits and explain
the readiness of study data with reproducible records? A fictional adult smoking study
has screening, documented consent/enrollment, control/app assignment, baseline, W04/W12
visits and14 daily EMA prompts. Eligibility requires age18+ and adequate self-reported use;
some eligible people decline. The generator includes screen-outs, refusals, withdrawals,
missed visits, skipped questions and delayed uploads. No real contact details are used.

## Schedule and outcomes

W04/W12 target dates are28/84 days after enrollment with ±7-day windows. The operational
completion numerator is an observed visit completion; it does not mean all outcome fields
are present or that abstinence was biochemically confirmed. Outcomes are illustrative
seven-day cigarette counts, self-reported abstinence, CO and daily urge/stress ratings.
Nicotine replacement is recorded as context. CO>6ppm with reported abstinence is a
**demo-protocol review flag**, not proof of smoking or a universal clinical cutoff.
See the SRNT methodological report: https://pmc.ncbi.nlm.nih.gov/articles/PMC7882145/ .

## Observation date and denominators

A visit becomes due when its window opens. The denominator includes enrolled visits with
opened windows as of the chosen date. A visit is pending while its window remains open;
overdue after its end. Withdrawal before/during its window removes an unfinished visit
from the due denominator. A missed visit accrued before withdrawal remains due. A recorded
completion before withdrawal counts. Future completions and future withdrawal status do
not appear as observed outcomes in historical queues. This is an explicit demonstration
policy, not a universal trial estimand. Duplicate participant/visit identities prevent a
completion-rate calculation until reconciled.

Expected-field missingness is separate: baseline fields on observed baselines, visit
measurements on observed completed visits and urge/stress on answered EMA. Declined,
missed and not-applicable EMA do not become item-missing ratings; the report also shows
overall EMA response. These conditional rates do not estimate all-source data loss.

## Research-assistant workflow

1. Load the synthetic study or initialize with the CLI. Keep the current source version.
2. Inspect the overview and dictionary; check counts and the observation date.
3. Review the quality findings. Structural/range/date errors differ from contextual review
   flags; a rule firing is not permission to alter a participant's response.
4. Consult a source form in a real setting. Here use the explicitly synthetic source or
   test case. Record a concise reason and reviewer for any supported correction.
5. Structural identity conflicts require reconciliation outside the field-edit form;
   editing row/participant keys is intentionally refused. No silent deduplication occurs.
6. Open follow-up, filter overdue/pending visits and document next steps in a study team's
   approved system. This demo's contacts are synthetic records; no outreach is sent.
7. Export the corrected tables/audit and generate the one-page report. Inspect denominators,
   missingness and limitations before presenting the report to a research team.

Original snapshots remain in SQLite `raw_records`; current records are separate. Audit
entries record old/new values, reason, reviewer and UTC time. Identical reimports preserve
corrections; conflicting raw records are refused transactionally. Exports do not include
the local SQLite database itself. There is no multiuser role/permission model in V1.

## Independent public-data case and literature record

The NHANES example uses public cross-sectional data and has no link to the synthetic
cohort. It demonstrates real joins, questionnaire skip logic, missing samples and below-LOD
flags. Literature/source evidence informing the project:

| Source | Design/measurement relevance | Project use | Limitation |
|---|---|---|---|
| HPRC Insight: https://healthpromotionresearch.org/Mobile-Health | EMA and digital health research operations | Daily repeated assessments and a follow-up queue | This app is independent of Insight |
| SRNT biochemical verification report: https://pmc.ncbi.nlm.nih.gov/articles/PMC7882145/ | Biomarker sources and detection windows | CO flags request context, not automatic outcome replacement | No clinical threshold validation here |
| CDC P_SMQ codebook: https://wwwn.cdc.gov/Nchs/Data/Nhanes/Public/2017/DataFiles/P_SMQ.htm | Lifetime/current cigarette questions and skip paths | Adult response classification, refusal/unknown separated | Self-report and lifetime100-cigarette grouping are not all-product nicotine use |
| CDC P_COT codebook: https://wwwn.cdc.gov/Nchs/Data/Nhanes/Public/2017/DataFiles/P_COT.htm | Serum measurements, LOD flags, survey design | Retain reported fill values and document missing serum | Cotinine includes nicotine exposure from different sources; unweighted summaries are sample-only |

No project artifact claims IRB approval, institutional validation, real participant
management, GCP certification, improved retention or treatment effectiveness.
