# V1 implementation contract

All identifiers refer to entirely synthetic people. Default as-of date: 2026-10-16.
Python package: `study_workbench`. DataBundle = `dict[str, pandas.DataFrame]`.
Dates are ISO calendar dates; EMA timestamps include UTC offsets. Empty CSV values are
missing, never an unknown numeric sentinel. Boolean fields use 0/1. No real contact info.

## Tables and columns (row_id unique per table)

- participants: row_id, participant_id, age, screening_date, eligible, eligibility_reason,
  consent_date, enrollment_date, arm, withdrawal_date, withdrawal_reason.
  arm is control/app or missing; eligibility reason is eligible/underage/low_use/declined.
- baseline: row_id, participant_id, assessed_at, cigarettes_per_day, readiness, co_ppm,
  nicotine_replacement. Ranges: age 18–100 for eligible people, cigarettes 0–100,
  readiness 0–10, CO 0–100 ppm, nicotine_replacement 0/1.
- visits: row_id, participant_id, visit_code, target_date, window_start, window_end,
  completed_at, status, cigarettes_7d, abstinent_7d, co_ppm, missing_reason.
  Codes W04/W12. status completed/scheduled/missed/withdrawn. Counts 0–700;
  abstinent_7d 0/1. Missing reasons blank/declined/unable_to_reach/technical/not_applicable.
- ema: row_id, participant_id, prompted_at, responded_at, uploaded_at, urge, stress,
  response_state. State answered/missed/declined/not_applicable; urge/stress 0–10.
- contacts: row_id, participant_id, contacted_at, channel, outcome, note.
  channel phone/email; outcome reached/no_answer/declined. No messages are sent.

## Interfaces and ownership

Data/quality agent owns schema.py, synthetic.py, quality.py, tests/test_quality.py,
tests/test_synthetic.py, docs/data_dictionary.csv, docs/QUALITY_RULES.md.

- schema.py: TABLE_COLUMNS: dict[str,list[str]], load_bundle(path)->DataBundle,
  save_bundle(bundle,path)->None. Validate schema and preserve row_id strings.
- synthetic.py: generate_clean(seed=42,n=240)->DataBundle;
  inject_errors(clean)->tuple[DataBundle,pd.DataFrame];
  generate_demo(output_dir,seed=42,n=240)->dict paths/counts. Save clean/, dirty/,
  truth.csv. Truth columns table,row_id,field,rule_id. Keep labels outside runtime engine.
- quality.py: check_bundle(bundle)->pd.DataFrame. Always return columns
  issue_id,rule_id,severity,table,row_id,participant_id,field,message.
  Severity error/review. evaluate(findings,truth)->dict with overall and per-rule TP/FP/FN,
  precision/recall. Match on (rule_id,table,row_id,field), deduplicate matches.
  Clean data and legitimate skip/late upload cases must produce no errors/reviews.

NHANES agent owns nhanes.py, tests/test_nhanes.py, docs/NHANES_METHODS.md.
- run_analysis(output_dir,cache_dir=None)->dict. Independently download P_DEMO,
  P_SMQ, P_COT official CDC 2017–March2020 XPT files. Source URLs, SHA256, retrieval
  time, counts, code mappings and limitations. Output summary.json, report.html,
  sample_summary.csv. Public case is descriptive, not a trial or clinical classifier.
- No dependencies beyond pandas/numpy/standard library. No UI coupling.

UI/reporting agent owns app.py, ui.py, reporting.py, tests/test_app.py.
- app.py imports study_workbench.ui.main.
- reporting.py: build_summary(bundle,as_of='2026-10-16')->dict;
  render_report(bundle,issues,as_of='2026-10-16')->str (standalone escaped HTML).
- UI uses Storage and followup interfaces below; provide overview, quality, follow-up,
  corrections/audit, data dictionary, public-data analysis, reports. English UI and
  strong synthetic labels. No network download at import/app startup. HTML/CSV exports.

Primary agent owns storage.py, followup.py, cli.py, integration, release evidence/docs.
- Storage(db_path): import_bundle(bundle,source_name='demo')->dict inserted/unchanged;
  load_bundle()->DataBundle; correct(table,row_id,field,new_value,reason,actor)->dict;
  audit_log()->pd.DataFrame; export_bundle(path)->None. Reason/actor required;
  immutable raw import snapshot; corrections transactional; reject unknown fields,
  structural keys, malformed types and invalid ranges. Idempotent import must not erase
  corrections. Do not overwrite an initialized database silently.
- followup.py: followup_status(bundle,as_of='2026-10-16')->pd.DataFrame with original
  visit fields plus computed_status (completed/pending/overdue/withdrawn/not_enrolled),
  due (bool), days_overdue. Completion only counts if completed_at<=as_of; records later
  than as_of cannot reveal a future completion. Exclude withdrawals before window_start
  from due denominator; keep accrued missed visits if withdrawal is after window_end.
- followup_metrics(bundle,as_of)->dict due_visits,completed_due_visits,
  completion_rate (None if no due visits),overdue_visits,withdrawn_visits.

## Release evidence

Relevant tests, independently labelled defects/clean special cases, SQLite restart and
audit tests, Streamlit AppTest and browser smoke, generated one-page study report,
source manifest and actual NHANES sample case, final bilingual portfolio/job-fit report.
Commit and push at runnable milestones and verify remote SHA. No invented success
metrics; note synthetic benchmark and sample-description limits in reports/resume text.
