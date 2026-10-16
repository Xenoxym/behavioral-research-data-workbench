"""Visit status at a fixed observation date, without future completion leakage."""
from __future__ import annotations

from datetime import date
import pandas as pd


def _calendar(value):
    if pd.isna(value):
        return pd.NaT
    try:
        text = str(value)
        parsed = date.fromisoformat(text)
        return pd.Timestamp(parsed) if parsed.isoformat() == text else pd.NaT
    except (TypeError, ValueError):
        return pd.NaT


def followup_status(bundle: dict, as_of: str = "2026-10-16") -> pd.DataFrame:
    cutoff = _calendar(as_of)
    if pd.isna(cutoff):
        raise ValueError("as_of must be an ISO calendar date")
    visits = bundle["visits"].copy()
    people = bundle["participants"]
    if people["participant_id"].duplicated().any():
        # Ambiguous joins must not silently multiply denominators.
        raise ValueError("Resolve duplicate participant IDs before calculating follow-up")
    if visits["row_id"].duplicated().any() or visits.duplicated(["participant_id", "visit_code"]).any():
        raise ValueError("Resolve duplicate visit events before calculating follow-up")
    people = people.set_index("participant_id")
    statuses, dues, delays = [], [], []
    for _, row in visits.iterrows():
        participant = people.loc[row["participant_id"]] if row["participant_id"] in people.index else None
        start = _calendar(row["window_start"])
        end = _calendar(row["window_end"])
        done = _calendar(row["completed_at"])
        enrolled = _calendar(participant["enrollment_date"]) if participant is not None else pd.NaT
        withdrawn = _calendar(participant["withdrawal_date"]) if participant is not None else pd.NaT
        if participant is None or pd.isna(enrolled) or enrolled > cutoff:
            status, due, delay = "not_enrolled", False, 0
        elif pd.isna(start) or pd.isna(end) or start > end:
            status, due, delay = "invalid_schedule", False, 0
        elif pd.notna(withdrawn) and withdrawn <= cutoff and withdrawn < start:
            status, due, delay = "withdrawn", False, 0
        elif pd.notna(done) and done <= cutoff and (pd.isna(withdrawn) or done <= withdrawn):
            status, due, delay = "completed", bool(start <= cutoff), 0
        elif pd.notna(withdrawn) and withdrawn <= cutoff:
            # A visit already overdue on withdrawal stays in the accrued denominator.
            accrued = bool(end < withdrawn and end < cutoff)
            status, due = "overdue" if accrued else "withdrawn", accrued
            delay = int((min(withdrawn, cutoff) - end).days) if accrued else 0
        elif cutoff > end:
            status, due, delay = "overdue", True, int((cutoff - end).days)
        else:
            status, due, delay = "pending", bool(start <= cutoff), 0
        statuses.append(status)
        dues.append(due)
        delays.append(delay)
    visits["computed_status"] = statuses
    visits["due"] = pd.Series(dues, index=visits.index, dtype=bool)
    visits["days_overdue"] = delays
    # Do not expose future observed outcomes in a historical work queue or export.
    future = visits["completed_at"].map(_calendar) > cutoff
    for field in ["completed_at", "cigarettes_7d", "abstinent_7d", "co_ppm"]:
        visits.loc[future, field] = pd.NA
    visits.loc[future, "status"] = "scheduled"
    visits.loc[future, "missing_reason"] = pd.NA
    future_withdrawal = visits["participant_id"].map(people["withdrawal_date"]).map(_calendar) > cutoff
    hide_withdrawal = future_withdrawal & visits["status"].eq("withdrawn")
    visits.loc[hide_withdrawal, "status"] = "scheduled"
    visits.loc[hide_withdrawal, "missing_reason"] = pd.NA
    return visits


def followup_metrics(bundle: dict, as_of: str = "2026-10-16") -> dict:
    visits = followup_status(bundle, as_of)
    due = int(visits["due"].sum())
    complete = int((visits["due"] & visits["computed_status"].eq("completed")).sum())
    return {
        "as_of": as_of,
        "due_visits": due,
        "completed_due_visits": complete,
        "completion_rate": complete / due if due else None,
        "overdue_visits": int(visits["computed_status"].eq("overdue").sum()),
        "withdrawn_visits": int(visits["computed_status"].eq("withdrawn").sum()),
        "pending_visits": int(visits["computed_status"].eq("pending").sum()),
        "denominator_definition": "Windows opened by as-of; exclude withdrawals during/before window unless already overdue at withdrawal; numerator includes observed completions only.",
    }
