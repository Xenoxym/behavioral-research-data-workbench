# Data quality benchmark and demonstration protocol

All longitudinal records are synthetic. The quality engine is deterministic and
does not receive truth labels. It reports errors requiring reconciliation and
review flags requiring interpretation. It never changes records automatically.
Public NHANES data are kept separate and do not enter these trial rules.

## Rule catalogue

| Rule ID | Severity | Trigger |
| --- | --- | --- |
| DUPLICATE_ROW_ID | error | Repeated source row key within a table; flag ambiguous key group once. |
| DUPLICATE_ID | error | Repeated screened participant identifier; flag every member. |
| DUPLICATE_EVENT | error | Multiple baseline records or repeated participant/visit or participant/EMA-prompt keys. EMA prompt keys use absolute timestamps. |
| MISSING_REQUIRED | error | Required item absent, including conditional consent, assignment, completed measurements and answered EMA content. |
| INVALID_NUMBER | error | A nonempty numeric field cannot be interpreted as a finite number. |
| RANGE | error | Numeric value outside documented range, or fractional value for an integer field. |
| INVALID_CATEGORY | error | Nonempty category is outside the explicit data dictionary. |
| INVALID_DATE | error | Calendar date is not valid ISO YYYY-MM-DD, or EMA timestamp lacks valid ISO time and offset. |
| AGE_ELIGIBILITY | error | An eligible participant is younger than 18 under the demo criteria. |
| ELIGIBILITY_REASON | error | Eligibility decision and reason conflict. |
| ELIGIBILITY_CONFLICT | error | Ineligible screen is enrolled. |
| DATE_ORDER | error | Consent before screening, enrollment before consent, baseline before enrollment, visit target before enrollment, contact before screening, EMA response before prompt, upload before response, or prompt before enrollment. |
| ASSIGNMENT_CONFLICT | error | Arm recorded without enrollment. |
| WITHDRAWAL_CONFLICT | error | Withdrawal predates/has no enrollment, reason has no date, or visit withdrawal has no corresponding participant withdrawal. |
| AFTER_WITHDRAWAL | error | Baseline/visit completion or EMA prompt occurs after recorded withdrawal. |
| MISSING_BASELINE | error | Enrolled person lacks a baseline record. |
| MISSING_VISIT | error | Enrolled person lacks at least one planned W04/W12 event row. |
| PARTICIPANT_ORPHAN | error | Child record references an unknown participant identifier. |
| NOT_ENROLLED | error | Research record references a screened person with no enrollment. Contact logs may reference any screened person. |
| WINDOW_ORDER | error | Target does not lie between visit window boundaries. |
| STATUS_CONFLICT | error | Noncompleted visit has a completion date. |
| NONCOMPLETED_DATA | error | Noncompleted visit without a completion date contains outcome measurements. |
| NONRESPONSE_DATA | error | Nonanswered EMA contains response time or ratings. |
| ABSTINENCE_CONFLICT | error | Seven-day abstinence says yes while reported cigarette count is positive. |
| BIOCHEMICAL_REVIEW | review | Self-reported abstinence accompanies CO >6 ppm. This configurable-in-code demonstration threshold asks for contextual review and is not a clinical determination. |
| VISIT_OUTSIDE_WINDOW | review | Completed visit falls outside its own protocol window. |

## Legitimate special cases

Underage/low-use screen-outs and eligible decliners need no baseline or visits.
The generator creates NRT use, reason-coded declined CO assessments, missed,
declined and structurally inapplicable EMA responses, and delayed offline uploads.
Those cases produce no findings in the clean dataset. A missing answered EMA item
is a defect; a missing structurally skipped rating is not. All outcomes can reach
their documented numeric bounds. Arm has no simulated effect.

An empty CSV cell is missing, never a sentinel value. Literal text such as `NA`
is preserved. Numeric CSV strings are parsed by the checks so invalid text is not
silently discarded. Corrections require a reason and actor in the SQLite layer.

## Independent evaluation

`generate_clean(seed=42, n=240)` creates a reproducible fixed-date cohort of 240
screened people. `inject_errors(clean)` copies it and applies explicit mutations.
Its expected labels are authored with the mutations, without invoking the checker.
Labels are written only to `truth.csv`, outside runtime tables.

The default benchmark contains **42 distinct expected issue matches across 23
rule IDs**. These are issue matches, not 42 independently corrupted people: a
duplicated participant generates two member flags and a post-withdrawal visit can
generate both an error and a window review. Three other implemented rule IDs have
dedicated edge tests or are documented rule behavior, rather than planted default
benchmark labels. Do not describe 23 labelled rule IDs as all possible defects.

Matching uses `(rule_id, table, row_id, field)`, deduplicated on both sides. Report
TP = intersection, FP = unexpected predictions, FN = missed expected labels, plus
precision = TP/(TP+FP), recall = TP/(TP+FN). Undefined ratios are JSON null.
Per-rule results retain both errors and review flags. False positives are also
measured by running the complete checker against unmodified clean records.

Run `python -m pytest tests/test_quality.py tests/test_synthetic.py -q` after setup.
The release's `reports/quality` files record the actual run results. A perfect
score on this deliberately authored benchmark establishes reproducible rule
behavior, not clinical validity or performance on unseen study data. Some defects
cause several findings; resolving one may eliminate several labels. Arbitrary
external protocols, free-text semantics and intentionally plausible fabrications
are beyond the current rule set.

## Scope and scientific limits

The demo assumes adult consent before enrollment and baseline after enrollment;
real protocols can use different procedures. The scheduled windows and smoking
outcomes are illustrative rather than an approved trial protocol. CO alone cannot
determine smoking status; timing and other combustion exposures matter. NRT is
recorded for context, not used as an automatic exception to a CO review. This tool
does not provide clinical advice, an IRB-approved data capture system, electronic
signature compliance, secure participant messaging, or a diagnostic classifier.
