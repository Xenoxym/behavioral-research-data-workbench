import pandas as pd
import pytest

from study_workbench.followup import followup_metrics, followup_status


def bundle(completed=None, withdrawal=None, start="2026-10-10", end="2026-10-20"):
    return {
        "participants": pd.DataFrame([{"participant_id": "S1", "enrollment_date": "2026-09-01", "withdrawal_date": withdrawal}]),
        "visits": pd.DataFrame([{"row_id": "V1", "participant_id": "S1", "visit_code": "W04", "window_start": start, "window_end": end, "completed_at": completed, "status": "completed" if completed else "scheduled", "cigarettes_7d": 0 if completed else None, "abstinent_7d": 1 if completed else None, "co_ppm": 2 if completed else None, "missing_reason": None}]),
    }


def test_open_window_is_due_but_not_overdue():
    metrics = followup_metrics(bundle(), "2026-10-16")
    assert metrics["due_visits"] == 1
    assert metrics["overdue_visits"] == 0
    assert metrics["completion_rate"] == 0


def test_future_outcome_cannot_leak_into_historical_queue():
    value = bundle(completed="2026-10-18")
    old = followup_status(value, "2026-10-16").iloc[0]
    assert old["computed_status"] == "pending"
    assert pd.isna(old["completed_at"]) and pd.isna(old["abstinent_7d"])
    assert old["status"] == "scheduled"
    assert followup_metrics(value, "2026-10-19")["completed_due_visits"] == 1


@pytest.mark.parametrize("withdrawal", ["2026-10-01", "2026-10-12"])
def test_withdrawal_before_or_during_window_excluded(withdrawal):
    assert followup_metrics(bundle(withdrawal=withdrawal), "2026-10-16")["due_visits"] == 0


def test_accrued_missed_visit_remains_after_withdrawal():
    metrics = followup_metrics(bundle(withdrawal="2026-10-14", end="2026-10-12"), "2026-10-16")
    assert metrics["due_visits"] == metrics["overdue_visits"] == 1


def test_not_yet_due_is_not_failure_or_missing_completion():
    metrics = followup_metrics(bundle(start="2026-11-01", end="2026-11-08"), "2026-10-16")
    assert metrics["due_visits"] == 0 and metrics["completion_rate"] is None


def test_completed_before_withdrawal_counts():
    assert followup_metrics(bundle(completed="2026-10-11", withdrawal="2026-10-12"), "2026-10-16")["completed_due_visits"] == 1


def test_duplicate_people_refused_to_protect_denominator():
    value = bundle()
    value["participants"] = pd.concat([value["participants"]] * 2)
    with pytest.raises(ValueError, match="duplicate"):
        followup_metrics(value)


def test_invalid_window_not_silently_included():
    value = followup_status(bundle(start="bad-date"))
    assert value.iloc[0]["computed_status"] == "invalid_schedule"
    assert not value.iloc[0]["due"]


def test_duplicate_event_cannot_change_completion_rate():
    value = bundle(completed="2026-10-11")
    duplicate = value["visits"].copy()
    duplicate["row_id"] = "V2"
    value["visits"] = pd.concat([value["visits"], duplicate], ignore_index=True)
    with pytest.raises(ValueError, match="duplicate visit"):
        followup_metrics(value)


def test_timestamp_in_calendar_field_is_invalid_schedule_not_crash():
    assert followup_status(bundle(start="2026-10-10T00:00:00+00:00")).iloc[0]["computed_status"] == "invalid_schedule"


def test_future_withdrawal_not_visible_in_historical_work_queue():
    value = bundle(withdrawal="2026-10-18", start="2026-10-20", end="2026-10-27")
    value["visits"]["status"] = "withdrawn"
    value["visits"]["missing_reason"] = "not_applicable"
    row = followup_status(value, "2026-10-16").iloc[0]
    assert row["computed_status"] == "pending"
    assert row["status"] == "scheduled" and pd.isna(row["missing_reason"])
