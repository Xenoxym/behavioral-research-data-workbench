"""Portable CSV contract for synthetic study records (no actual participant data)."""
from pathlib import Path
import pandas as pd

DataBundle = dict[str, pd.DataFrame]
TABLE_COLUMNS = {
    "participants": ["row_id", "participant_id", "age", "screening_date", "eligible", "eligibility_reason", "consent_date", "enrollment_date", "arm", "withdrawal_date", "withdrawal_reason"],
    "baseline": ["row_id", "participant_id", "assessed_at", "cigarettes_per_day", "readiness", "co_ppm", "nicotine_replacement"],
    "visits": ["row_id", "participant_id", "visit_code", "target_date", "window_start", "window_end", "completed_at", "status", "cigarettes_7d", "abstinent_7d", "co_ppm", "missing_reason"],
    "ema": ["row_id", "participant_id", "prompted_at", "responded_at", "uploaded_at", "urge", "stress", "response_state"],
    "contacts": ["row_id", "participant_id", "contacted_at", "channel", "outcome", "note"],
}
NUMERIC_FIELDS = {
    "participants": ["age", "eligible"],
    "baseline": ["cigarettes_per_day", "readiness", "co_ppm", "nicotine_replacement"],
    "visits": ["cigarettes_7d", "abstinent_7d", "co_ppm"],
    "ema": ["urge", "stress"], "contacts": [],
}
DATE_FIELDS = {
    "participants": ["screening_date", "consent_date", "enrollment_date", "withdrawal_date"],
    "baseline": ["assessed_at"],
    "visits": ["target_date", "window_start", "window_end", "completed_at"],
    "ema": ["prompted_at", "responded_at", "uploaded_at"],
    "contacts": ["contacted_at"],
}


def validate_bundle(bundle: DataBundle) -> None:
    """Validate structure, while leaving record errors for the quality engine."""
    missing = set(TABLE_COLUMNS) - set(bundle)
    extra = set(bundle) - set(TABLE_COLUMNS)
    if missing or extra:
        raise ValueError(f"Table mismatch: missing={sorted(missing)}, extra={sorted(extra)}")
    for table, columns in TABLE_COLUMNS.items():
        actual = list(bundle[table].columns)
        if len(actual) != len(set(actual)) or set(actual) != set(columns):
            raise ValueError(f"Column mismatch in {table}: expected {columns}, got {actual}")


def load_bundle(path: str | Path) -> DataBundle:
    """Load all five tables without stripping leading zeros or coercing bad values.

    Numeric strings remain strings so malformed imported data can be reviewed.
    Only empty CSV fields are missing; literal strings such as NA are preserved.
    """
    root = Path(path)
    bundle = {table: pd.read_csv(root / f"{table}.csv", dtype=str,
                                keep_default_na=False, na_values=[""])
              for table in TABLE_COLUMNS}
    validate_bundle(bundle)
    return bundle


def save_bundle(bundle: DataBundle, path: str | Path) -> None:
    validate_bundle(bundle)
    root = Path(path)
    root.mkdir(parents=True, exist_ok=True)
    for table, columns in TABLE_COLUMNS.items():
        bundle[table].loc[:, columns].to_csv(root / f"{table}.csv", index=False)
