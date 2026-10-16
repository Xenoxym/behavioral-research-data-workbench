"""Deterministic, transparent checks for the demonstration protocol.

There is intentionally no truth-label input to ``check_bundle``. Review flags ask
for a human review; they do not determine smoking status or make diagnoses.
"""
from hashlib import sha256
import math
import re
import pandas as pd
from .schema import DATE_FIELDS, validate_bundle

ISSUE_COLUMNS = ["issue_id", "rule_id", "severity", "table", "row_id", "participant_id", "field", "message"]
MATCH_COLUMNS = ["rule_id", "table", "row_id", "field"]
REQUIRED = {
    "participants": ["row_id", "participant_id", "age", "screening_date", "eligible", "eligibility_reason"],
    "baseline": ["row_id", "participant_id", "assessed_at", "cigarettes_per_day", "readiness", "co_ppm", "nicotine_replacement"],
    "visits": ["row_id", "participant_id", "visit_code", "target_date", "window_start", "window_end", "status"],
    "ema": ["row_id", "participant_id", "prompted_at", "response_state"],
    "contacts": ["row_id", "participant_id", "contacted_at", "channel", "outcome"],
}
RANGES = {
    "participants": {"age": (0, 100, True), "eligible": (0, 1, True)},
    "baseline": {"cigarettes_per_day": (0, 100, True), "readiness": (0, 10, True), "co_ppm": (0, 100, False), "nicotine_replacement": (0, 1, True)},
    "visits": {"cigarettes_7d": (0, 700, True), "abstinent_7d": (0, 1, True), "co_ppm": (0, 100, False)},
    "ema": {"urge": (0, 10, True), "stress": (0, 10, True)}, "contacts": {},
}
ENUMS = {
    "participants": {"eligibility_reason": {"eligible", "underage", "low_use", "declined"}, "arm": {"control", "app"}},
    "visits": {"visit_code": {"W04", "W12"}, "status": {"completed", "scheduled", "missed", "withdrawn"}, "missing_reason": {"declined", "unable_to_reach", "technical", "not_applicable"}},
    "ema": {"response_state": {"answered", "missed", "declined", "not_applicable"}},
    "contacts": {"channel": {"phone", "email"}, "outcome": {"reached", "no_answer", "declined"}},
    "baseline": {},
}


def _blank(value):
    return pd.isna(value) or (isinstance(value, str) and not value.strip())


def _num(value):
    if _blank(value):
        return None
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def _date(value):
    if _blank(value):
        return None
    # Reject locale-dependent dates and relative words such as 'today'.
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2}))?", str(value)):
        return None
    try:
        timestamp = pd.Timestamp(value)
        if pd.isna(timestamp):
            return None
        return timestamp.tz_localize("UTC") if timestamp.tzinfo is None else timestamp.tz_convert("UTC")
    except (TypeError, ValueError, OverflowError):
        return None


def check_bundle(bundle):
    """Return one stable issue per (rule, table, row_id, field).

    All flagged fields refer to real source columns. Duplicate row IDs necessarily
    identify an ambiguous group; resolve those before applying row corrections.
    """
    validate_bundle(bundle)
    bundle = {table: data.astype(object).where(data.notna(), None) for table, data in bundle.items()}
    findings = {}

    def add(rule, table, row, field, message, severity="error"):
        key = (rule, table, str(row["row_id"]), field)
        findings[key] = {
            "issue_id": sha256("|".join(key).encode()).hexdigest()[:16],
            "rule_id": rule, "severity": severity, "table": table,
            "row_id": str(row["row_id"]), "participant_id": str(row["participant_id"]),
            "field": field, "message": message,
        }

    for table, data in bundle.items():
        for field in ["row_id"] + (["participant_id"] if table == "participants" else []):
            rule = "DUPLICATE_ROW_ID" if field == "row_id" else "DUPLICATE_ID"
            mask = data[field].duplicated(keep=False) & ~data[field].map(_blank)
            for _, row in data[mask].iterrows():
                add(rule, table, row, field, f"Repeated {field}; reconcile the source records.")
        event_keys = {"baseline": ["participant_id"], "visits": ["participant_id", "visit_code"], "ema": ["participant_id", "prompted_at"]}.get(table)
        if event_keys:
            events = data[event_keys].copy()
            if table == "ema":
                events["prompted_at"] = events.prompted_at.map(_date)
            complete_keys = ~events.map(_blank).any(axis=1)
            for _, row in data[events.duplicated(event_keys, keep=False) & complete_keys].iterrows():
                add("DUPLICATE_EVENT", table, row, "participant_id", "Repeated participant/event key.")
        for _, row in data.iterrows():
            for field in REQUIRED[table]:
                if _blank(row[field]):
                    add("MISSING_REQUIRED", table, row, field, f"Required field {field} is empty.")
            for field, (lower, upper, integer) in RANGES[table].items():
                if not _blank(row[field]):
                    number = _num(row[field])
                    if number is None:
                        add("INVALID_NUMBER", table, row, field, "Value must be a finite number.")
                    elif number < lower or number > upper or (integer and not number.is_integer()):
                        add("RANGE", table, row, field, f"Expected {'integer' if integer else 'number'} in [{lower}, {upper}].")
            for field, values in ENUMS[table].items():
                if not _blank(row[field]) and row[field] not in values:
                    add("INVALID_CATEGORY", table, row, field, f"Expected one of {', '.join(sorted(values))}.")
            for field in DATE_FIELDS[table]:
                if not _blank(row[field]) and (_date(row[field]) is None or
                     (table == "ema" and "T" not in str(row[field])) or
                     (table != "ema" and len(str(row[field])) != 10)):
                    add("INVALID_DATE", table, row, field, "Date or timestamp cannot be parsed.")

    # A duplicate ID is already reported; choose first only to avoid merge expansion.
    participant_map = {str(row["participant_id"]): row for _, row in bundle["participants"].iloc[::-1].iterrows() if not _blank(row["participant_id"])}
    baseline_ids = set(bundle["baseline"]["participant_id"].astype(str))
    visit_groups = bundle["visits"].groupby("participant_id")["visit_code"].agg(set).to_dict()

    for _, row in bundle["participants"].iterrows():
        table = "participants"
        screen, consent, enrolled, withdrawn = [_date(row[field]) for field in ["screening_date", "consent_date", "enrollment_date", "withdrawal_date"]]
        eligible, age = _num(row["eligible"]), _num(row["age"])
        if eligible == 1 and age is not None and age < 18:
            add("AGE_ELIGIBILITY", table, row, "age", "An eligible participant must be at least 18 under the demo protocol.")
        if (eligible == 1 and row["eligibility_reason"] not in {"eligible", "declined"}) or (eligible == 0 and row["eligibility_reason"] in {"eligible", "declined"}):
            add("ELIGIBILITY_REASON", table, row, "eligibility_reason", "Eligibility flag and reason disagree.")
        if enrolled is not None:
            if eligible == 0:
                add("ELIGIBILITY_CONFLICT", table, row, "eligible", "An ineligible screen must not be enrolled.")
            for field in ["consent_date", "arm"]:
                if _blank(row[field]):
                    add("MISSING_REQUIRED", table, row, field, "Enrollment requires documented consent and assignment.")
            if consent is not None and enrolled < consent:
                add("DATE_ORDER", table, row, "enrollment_date", "Enrollment precedes consent.")
            if str(row["participant_id"]) not in baseline_ids:
                add("MISSING_BASELINE", table, row, "participant_id", "Enrolled participant has no baseline record.")
            if not {"W04", "W12"}.issubset(visit_groups.get(row["participant_id"], set())):
                add("MISSING_VISIT", table, row, "participant_id", "Enrolled participant lacks a planned W04 or W12 visit record.")
        elif not _blank(row["arm"]):
            add("ASSIGNMENT_CONFLICT", table, row, "arm", "Study assignment exists without an enrollment date.")
        if screen is not None and consent is not None and consent < screen:
            add("DATE_ORDER", table, row, "consent_date", "Consent precedes screening.")
        if withdrawn is not None:
            if enrolled is None or withdrawn < enrolled:
                add("WITHDRAWAL_CONFLICT", table, row, "withdrawal_date", "Withdrawal requires an earlier enrollment.")
            if _blank(row["withdrawal_reason"]):
                add("MISSING_REQUIRED", table, row, "withdrawal_reason", "Document the withdrawal reason.")
        elif not _blank(row["withdrawal_reason"]):
            add("WITHDRAWAL_CONFLICT", table, row, "withdrawal_reason", "Withdrawal reason exists without a date.")

    for table in ["baseline", "visits", "ema", "contacts"]:
        for _, row in bundle[table].iterrows():
            person = participant_map.get(str(row["participant_id"]))
            if person is None:
                if not _blank(row["participant_id"]):
                    add("PARTICIPANT_ORPHAN", table, row, "participant_id", "No matching participant screening record.")
                continue
            enrolled, withdrawn = _date(person["enrollment_date"]), _date(person["withdrawal_date"])
            if table != "contacts" and enrolled is None:
                add("NOT_ENROLLED", table, row, "participant_id", "Research event has no documented enrollment.")
            if table == "baseline":
                assessed = _date(row["assessed_at"])
                if assessed is not None and enrolled is not None and assessed < enrolled:
                    add("DATE_ORDER", table, row, "assessed_at", "Baseline precedes enrollment.")
                if assessed is not None and withdrawn is not None and assessed > withdrawn:
                    add("AFTER_WITHDRAWAL", table, row, "assessed_at", "Research assessment is after withdrawal.")
            elif table == "visits":
                target, start, end, completed = [_date(row[field]) for field in ["target_date", "window_start", "window_end", "completed_at"]]
                if target is not None and start is not None and end is not None and not start <= target <= end:
                    add("WINDOW_ORDER", table, row, "target_date", "Target must lie between window start and end.")
                if target is not None and enrolled is not None and target < enrolled:
                    add("DATE_ORDER", table, row, "target_date", "Visit target precedes enrollment.")
                if row["status"] == "completed":
                    if _blank(row["completed_at"]):
                        add("MISSING_REQUIRED", table, row, "completed_at", "Completed visit requires a completion date.")
                    if row["missing_reason"] not in {"declined", "technical"}:
                        for field in ["cigarettes_7d", "abstinent_7d", "co_ppm"]:
                            if _blank(row[field]):
                                add("MISSING_REQUIRED", table, row, field, "Completed measurement is missing without declined/technical reason.")
                    if completed is not None and start is not None and end is not None and not start <= completed <= end:
                        add("VISIT_OUTSIDE_WINDOW", table, row, "completed_at", "Completion falls outside its protocol window; review deviation.", "review")
                elif not _blank(row["completed_at"]):
                    add("STATUS_CONFLICT", table, row, "status", "A noncompleted visit has a completion date.")
                else:
                    for field in ["cigarettes_7d", "abstinent_7d", "co_ppm"]:
                        if not _blank(row[field]):
                            add("NONCOMPLETED_DATA", table, row, field, "Uncompleted visit contains an outcome measurement.")
                if row["status"] in {"missed", "withdrawn"} and _blank(row["missing_reason"]):
                    add("MISSING_REQUIRED", table, row, "missing_reason", "Missed/withdrawn visit requires a missingness reason.")
                if row["status"] == "withdrawn" and withdrawn is None:
                    add("WITHDRAWAL_CONFLICT", table, row, "status", "Visit says withdrawn but participant has no withdrawal date.")
                if completed is not None and withdrawn is not None and completed > withdrawn:
                    add("AFTER_WITHDRAWAL", table, row, "completed_at", "Visit completion follows withdrawal.")
                if _num(row["abstinent_7d"]) == 1:
                    if (_num(row["cigarettes_7d"]) or 0) > 0:
                        add("ABSTINENCE_CONFLICT", table, row, "abstinent_7d", "Self-reported abstinence conflicts with nonzero seven-day count.")
                    if (_num(row["co_ppm"]) or 0) > 6:
                        add("BIOCHEMICAL_REVIEW", table, row, "co_ppm", "Self-reported abstinence with CO >6 ppm requires contextual review; this is not a diagnosis.", "review")
            elif table == "ema":
                prompted, responded, uploaded = [_date(row[field]) for field in ["prompted_at", "responded_at", "uploaded_at"]]
                if row["response_state"] == "answered":
                    for field in ["responded_at", "uploaded_at", "urge", "stress"]:
                        if _blank(row[field]):
                            add("MISSING_REQUIRED", table, row, field, "Answered EMA requires response time, upload time and ratings.")
                else:
                    for field in ["responded_at", "urge", "stress"]:
                        if not _blank(row[field]):
                            add("NONRESPONSE_DATA", table, row, field, "Skipped EMA contains response content.")
                if prompted is not None and responded is not None and responded < prompted:
                    add("DATE_ORDER", table, row, "responded_at", "EMA response precedes prompt.")
                if responded is not None and uploaded is not None and uploaded < responded:
                    add("DATE_ORDER", table, row, "uploaded_at", "Upload precedes response. Delayed uploads are permitted.")
                if prompted is not None and enrolled is not None and prompted < enrolled:
                    add("DATE_ORDER", table, row, "prompted_at", "EMA prompt precedes enrollment.")
                if prompted is not None and withdrawn is not None and prompted.normalize() > withdrawn.normalize():
                    add("AFTER_WITHDRAWAL", table, row, "prompted_at", "Research prompt follows withdrawal.")
            elif table == "contacts":
                contact, screen = _date(row["contacted_at"]), _date(person["screening_date"])
                if contact is not None and screen is not None and contact < screen:
                    add("DATE_ORDER", table, row, "contacted_at", "Contact log precedes its screening/referral record.")
    return pd.DataFrame(list(findings.values()), columns=ISSUE_COLUMNS).sort_values(
        ["table", "row_id", "rule_id", "field"], ignore_index=True)


def evaluate(findings: pd.DataFrame, truth: pd.DataFrame) -> dict:
    """Set matching prevents duplicate alarms from inflating benchmark performance."""
    def keys(frame):
        if not set(MATCH_COLUMNS).issubset(frame.columns):
            raise ValueError(f"Evaluation requires {MATCH_COLUMNS}")
        return {tuple(str(value) for value in row) for row in frame[MATCH_COLUMNS].itertuples(index=False, name=None)}
    predicted, expected = keys(findings), keys(truth)

    def score(found, labelled):
        tp, fp, fn = len(found & labelled), len(found - labelled), len(labelled - found)
        return {"tp": tp, "fp": fp, "fn": fn, "precision": tp / (tp + fp) if tp + fp else None,
                "recall": tp / (tp + fn) if tp + fn else None}
    rules = sorted({key[0] for key in predicted | expected})
    return {"overall": score(predicted, expected), "per_rule": [
        {"rule_id": rule, **score({key for key in predicted if key[0] == rule}, {key for key in expected if key[0] == rule})}
        for rule in rules]}
