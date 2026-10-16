from datetime import timedelta
import pandas as pd
import pytest
from study_workbench.quality import ISSUE_COLUMNS, check_bundle, evaluate
from study_workbench.schema import load_bundle, save_bundle
from study_workbench.synthetic import generate_clean, inject_errors


@pytest.fixture
def clean():
    return generate_clean()


@pytest.mark.parametrize("seed,n", [(42, 240), (7, 60), (2026, 1), (123, 500)])
def test_clean_and_legitimate_special_cases_are_unflagged(seed, n):
    findings = check_bundle(generate_clean(seed=seed, n=n))
    assert list(findings.columns) == ISSUE_COLUMNS
    assert findings.empty, findings.to_string(index=False)


def test_independently_labelled_benchmark(clean):
    dirty, truth = inject_errors(clean)
    result = evaluate(check_bundle(dirty), truth)
    assert result["overall"] == {"tp": 42, "fp": 0, "fn": 0, "precision": 1.0, "recall": 1.0}
    assert len(result["per_rule"]) == 23
    assert all(row["fp"] == row["fn"] == 0 for row in result["per_rule"])


def test_csv_roundtrip_has_same_benchmark(clean, tmp_path):
    dirty, truth = inject_errors(clean)
    save_bundle(dirty, tmp_path)
    loaded = load_bundle(tmp_path)
    assert evaluate(check_bundle(loaded), truth)["overall"]["tp"] == 42
    assert evaluate(check_bundle(loaded), truth)["overall"]["fp"] == 0


def test_labels_do_not_control_engine_and_issue_ids_are_stable(clean):
    dirty, _ = inject_errors(clean)
    first, second = check_bundle(dirty), check_bundle(dirty)
    pd.testing.assert_frame_equal(first, second)
    assert first.issue_id.is_unique
    assert set(first.severity) == {"error", "review"}


def test_evaluator_counts_missed_and_false_flags_and_deduplicates():
    truth = pd.DataFrame([
        {"table": "baseline", "row_id": "B1", "field": "readiness", "rule_id": "RANGE"},
        {"table": "baseline", "row_id": "B2", "field": "co_ppm", "rule_id": "RANGE"},
    ])
    found = pd.concat([truth.iloc[[0]], truth.iloc[[0]], truth.iloc[[0]].assign(rule_id="OTHER")], ignore_index=True)
    score = evaluate(found, truth)["overall"]
    assert score == {"tp": 1, "fp": 1, "fn": 1, "precision": 0.5, "recall": 0.5}
    empty = truth.iloc[:0]
    assert evaluate(empty, empty)["overall"] == {"tp": 0, "fp": 0, "fn": 0, "precision": None, "recall": None}


def test_numeric_boundaries_are_valid_and_fractional_ratings_are_not(clean):
    clean["baseline"].loc[0, ["cigarettes_per_day", "readiness", "co_ppm", "nicotine_replacement"]] = [100, 0, 100, 1]
    clean["baseline"].loc[1, ["cigarettes_per_day", "readiness", "co_ppm", "nicotine_replacement"]] = [0, 10, 0, 0]
    assert check_bundle(clean).empty
    clean["baseline"]["readiness"] = clean["baseline"].readiness.astype(object)
    clean["baseline"].loc[0, "readiness"] = 5.5
    findings = check_bundle(clean)
    assert findings[["rule_id", "field"]].to_dict("records") == [{"rule_id": "RANGE", "field": "readiness"}]


@pytest.mark.parametrize("bad", ["today", "10/16/2026", "2026-02-30", "2026-07-01T12:00:00"])
def test_invalid_or_ambiguous_dates_are_rejected(clean, bad):
    clean["participants"].loc[0, "screening_date"] = bad
    assert "INVALID_DATE" in set(check_bundle(clean).rule_id)


def test_ema_timezones_and_late_upload_are_valid(clean):
    index = clean["ema"].query("response_state == 'answered'").index[0]
    row = clean["ema"].loc[index]
    responded = pd.Timestamp(row.responded_at).tz_convert("US/Eastern")
    clean["ema"].at[index, "responded_at"] = responded.isoformat()
    clean["ema"].at[index, "uploaded_at"] = (responded.to_pydatetime() + timedelta(days=10)).isoformat()
    assert check_bundle(clean).empty


def test_same_ema_instant_with_different_offset_is_duplicate(clean):
    duplicate = clean["ema"].iloc[0].copy()
    duplicate.row_id = "E-DUPLICATE"
    duplicate.prompted_at = pd.Timestamp(duplicate.prompted_at).tz_convert("US/Eastern").isoformat()
    clean["ema"] = pd.concat([clean["ema"], duplicate.to_frame().T], ignore_index=True)
    findings = check_bundle(clean)
    assert len(findings) == 2
    assert findings.rule_id.eq("DUPLICATE_EVENT").all()


def test_skipped_ema_and_declined_co_have_no_item_missing_flags(clean):
    assert check_bundle(clean).empty
    answered = clean["ema"].query("response_state == 'answered'").index[0]
    clean["ema"].at[answered, "stress"] = None
    issue = check_bundle(clean)
    assert len(issue) == 1
    assert issue.iloc[0].field == "stress"
    assert issue.iloc[0].rule_id == "MISSING_REQUIRED"


def test_pandas_missing_scalar_does_not_crash(clean):
    clean["visits"].loc[0, "status"] = pd.NA
    assert "MISSING_REQUIRED" in set(check_bundle(clean).rule_id)


def test_empty_tables_have_consistent_output():
    from study_workbench.schema import TABLE_COLUMNS
    bundle = {table: pd.DataFrame(columns=columns) for table, columns in TABLE_COLUMNS.items()}
    assert check_bundle(bundle).empty


@pytest.mark.parametrize("case,rule", [
    ("unassigned_enrollment", "ASSIGNMENT_CONFLICT"),
    ("withdrawal_without_date", "WITHDRAWAL_CONFLICT"),
    ("noncompleted_measurement", "NONCOMPLETED_DATA"),
])
def test_nonbenchmark_rules_with_independent_mutations(clean, case, rule):
    if case == "unassigned_enrollment":
        index = clean["participants"][clean["participants"].enrollment_date.isna()].index[0]
        clean["participants"].at[index, "arm"] = "control"
    elif case == "withdrawal_without_date":
        index = clean["participants"][clean["participants"].withdrawal_date.isna()].index[0]
        clean["participants"].at[index, "withdrawal_reason"] = "participant_request"
    else:
        index = clean["visits"].query("status == 'missed'").index[0]
        clean["visits"].at[index, "cigarettes_7d"] = 7
    findings = check_bundle(clean)
    assert len(findings) == 1
    assert findings.iloc[0].rule_id == rule
