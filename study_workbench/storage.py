"""Transactional local records with immutable raw snapshots and correction history."""
from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from .schema import TABLE_COLUMNS, NUMERIC_FIELDS, save_bundle

NUMERIC = {
    "age": (0, 100), "eligible": (0, 1), "cigarettes_per_day": (0, 100),
    "readiness": (0, 10), "co_ppm": (0, 100), "nicotine_replacement": (0, 1),
    "cigarettes_7d": (0, 700), "abstinent_7d": (0, 1), "urge": (0, 10), "stress": (0, 10),
}
INTEGERS = set(NUMERIC) - {"co_ppm"}
ENUMS = {
    "eligible": {0, 1}, "arm": {"control", "app"},
    "eligibility_reason": {"eligible", "underage", "low_use", "declined"},
    "visit_code": {"W04", "W12"},
    "status": {"completed", "scheduled", "missed", "withdrawn"},
    "response_state": {"answered", "missed", "declined", "not_applicable"},
    "missing_reason": {"declined", "unable_to_reach", "technical", "not_applicable"},
    "channel": {"phone", "email"}, "outcome": {"reached", "no_answer", "declined"},
}


def _value(value):
    if value is None or pd.isna(value):
        return None
    if hasattr(value, "item"):
        value = value.item()
    return value


def _serialize(row: dict) -> str:
    return json.dumps({k: _value(v) for k, v in row.items()}, sort_keys=True, ensure_ascii=False, allow_nan=False)


def _normalize_row(table, row):
    """CSV and in-memory imports share canonical types; malformed values stay inspectable."""
    row = {key: _value(value) for key, value in row.items()}
    for key in NUMERIC_FIELDS[table]:
        value = row[key]
        if value is None:
            continue
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(number):
            row[key] = int(number) if number.is_integer() and key in INTEGERS else number
    return row


class Storage:
    def __init__(self, db_path):
        self.path = Path(db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connection() as conn:
            conn.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS records (
                table_name TEXT NOT NULL, row_id TEXT NOT NULL, payload TEXT NOT NULL,
                PRIMARY KEY(table_name,row_id));
            CREATE TABLE IF NOT EXISTS raw_records (
                table_name TEXT NOT NULL, row_id TEXT NOT NULL, payload TEXT NOT NULL,
                source_name TEXT NOT NULL, imported_at TEXT NOT NULL,
                PRIMARY KEY(table_name,row_id));
            CREATE TABLE IF NOT EXISTS imports (
                digest TEXT PRIMARY KEY, source_name TEXT NOT NULL, imported_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS audit (
                audit_id INTEGER PRIMARY KEY AUTOINCREMENT, table_name TEXT NOT NULL,
                row_id TEXT NOT NULL, field TEXT NOT NULL, old_value TEXT, new_value TEXT,
                reason TEXT NOT NULL, actor TEXT NOT NULL, changed_at TEXT NOT NULL);
            CREATE TRIGGER IF NOT EXISTS raw_no_update BEFORE UPDATE ON raw_records
                BEGIN SELECT RAISE(ABORT,'Raw records are immutable'); END;
            CREATE TRIGGER IF NOT EXISTS raw_no_delete BEFORE DELETE ON raw_records
                BEGIN SELECT RAISE(ABORT,'Raw records are immutable'); END;
            CREATE TRIGGER IF NOT EXISTS audit_no_update BEFORE UPDATE ON audit
                BEGIN SELECT RAISE(ABORT,'Audit records are immutable'); END;
            CREATE TRIGGER IF NOT EXISTS audit_no_delete BEFORE DELETE ON audit
                BEGIN SELECT RAISE(ABORT,'Audit records are immutable'); END;
            """)

    @contextmanager
    def _connection(self):
        connection = sqlite3.connect(self.path, timeout=15)
        try:
            with connection:
                connection.row_factory = sqlite3.Row
                yield connection
        finally:
            connection.close()

    def import_bundle(self, bundle, source_name="demo") -> dict:
        if set(bundle) != set(TABLE_COLUMNS):
            raise ValueError("Import must contain exactly the documented tables")
        serialized = []
        for table, columns in TABLE_COLUMNS.items():
            frame = bundle[table]
            if set(frame.columns) != set(columns):
                raise ValueError(f"Invalid columns for {table}")
            if frame["row_id"].isna().any() or frame["row_id"].duplicated().any():
                raise ValueError(f"Import requires unique, nonmissing row_id in {table}")
            for row in frame[columns].to_dict("records"):
                key = str(row["row_id"])
                if not key.strip():
                    raise ValueError("Empty row_id")
                serialized.append((table, key, _serialize(_normalize_row(table, row))))
        serialized.sort()
        digest = hashlib.sha256(json.dumps(serialized).encode()).hexdigest()
        now = datetime.now(timezone.utc).isoformat()
        with self._connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            if conn.execute("SELECT 1 FROM imports WHERE digest=?", (digest,)).fetchone():
                return {"inserted": 0, "unchanged": len(serialized), "digest": digest}
            inserted = unchanged = 0
            for table, key, payload in serialized:
                existing = conn.execute("SELECT payload FROM raw_records WHERE table_name=? AND row_id=?", (table, key)).fetchone()
                if existing:
                    if existing["payload"] != payload:
                        raise ValueError(f"Conflicting raw record {table}/{key}; use a separate database or reasoned correction")
                    unchanged += 1
                    continue
                conn.execute("INSERT INTO raw_records VALUES (?,?,?,?,?)", (table, key, payload, source_name, now))
                conn.execute("INSERT INTO records VALUES (?,?,?)", (table, key, payload))
                inserted += 1
            conn.execute("INSERT INTO imports VALUES (?,?,?)", (digest, source_name, now))
        return {"inserted": inserted, "unchanged": unchanged, "digest": digest}

    def load_bundle(self, raw=False):
        result = {}
        source = "raw_records" if raw else "records"
        with self._connection() as conn:
            for table, columns in TABLE_COLUMNS.items():
                rows = conn.execute(f"SELECT payload FROM {source} WHERE table_name=? ORDER BY row_id", (table,)).fetchall()
                result[table] = pd.DataFrame([json.loads(r["payload"]) for r in rows], columns=columns)
        return result

    def correct(self, table, row_id, field, new_value, reason, actor):
        if table not in TABLE_COLUMNS or field not in TABLE_COLUMNS[table]:
            raise ValueError("Unknown table or field")
        if field in {"row_id", "participant_id"}:
            raise ValueError("Structural identifiers cannot be edited")
        if not str(reason or "").strip() or not str(actor or "").strip():
            raise ValueError("Actor and reason are required")
        value = None if new_value is None or str(new_value).strip() == "" else new_value
        if value is not None:
            if field in NUMERIC:
                try:
                    number = float(value)
                except (ValueError, TypeError) as exc:
                    raise ValueError("A numeric value is required") from exc
                low, high = NUMERIC[field]
                if not math.isfinite(number) or not low <= number <= high:
                    raise ValueError(f"{field} must be between {low} and {high}")
                if field in INTEGERS and not number.is_integer():
                    raise ValueError(f"{field} must be an integer")
                value = int(number) if field in INTEGERS else number
            elif field.endswith("_date") or field in {"assessed_at", "target_date", "window_start", "window_end", "completed_at", "contacted_at"}:
                try:
                    parsed = datetime.strptime(str(value), "%Y-%m-%d")
                except ValueError as exc:
                    raise ValueError("Use an ISO YYYY-MM-DD date") from exc
                value = parsed.date().isoformat()
            elif field in {"prompted_at", "responded_at", "uploaded_at"}:
                try:
                    parsed = datetime.fromisoformat(str(value))
                except ValueError as exc:
                    raise ValueError("Use a valid ISO timestamp with UTC offset") from exc
                if parsed.tzinfo is None:
                    raise ValueError("EMA timestamps require a UTC offset")
                value = parsed.isoformat()
            else:
                value = str(value).strip()
            if field in ENUMS and value not in ENUMS[field]:
                raise ValueError(f"Unsupported {field} value")
        with self._connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            record = conn.execute("SELECT payload FROM records WHERE table_name=? AND row_id=?", (table, str(row_id))).fetchone()
            if not record:
                raise ValueError("Record not found")
            row = json.loads(record["payload"])
            old = row[field]
            if old == value:
                raise ValueError("Correction does not change the value")
            # Hard chronology errors must not be introduced by a correction.
            candidate = dict(row, **{field: value})
            for earlier, later in [("consent_date", "enrollment_date"), ("enrollment_date", "withdrawal_date"), ("window_start", "window_end"), ("prompted_at", "responded_at"), ("responded_at", "uploaded_at")]:
                a, b = candidate.get(earlier), candidate.get(later)
                if a and b and pd.to_datetime(a, errors="coerce") > pd.to_datetime(b, errors="coerce"):
                    raise ValueError(f"{later} cannot precede {earlier}")
            now = datetime.now(timezone.utc).isoformat()
            conn.execute("UPDATE records SET payload=? WHERE table_name=? AND row_id=?", (_serialize(candidate), table, str(row_id)))
            cursor = conn.execute("INSERT INTO audit(table_name,row_id,field,old_value,new_value,reason,actor,changed_at) VALUES (?,?,?,?,?,?,?,?)", (table, str(row_id), field, json.dumps(old), json.dumps(value), str(reason).strip(), str(actor).strip(), now))
            return {"audit_id": cursor.lastrowid, "table": table, "row_id": str(row_id), "field": field, "old_value": old, "new_value": value, "reason": reason, "actor": actor, "changed_at": now}

    def audit_log(self):
        with self._connection() as conn:
            return pd.read_sql_query("SELECT * FROM audit ORDER BY audit_id", conn)

    def export_bundle(self, path):
        save_bundle(self.load_bundle(), path)
        target = Path(path)
        self.audit_log().to_csv(target / "audit_log.csv", index=False)
        manifest = {"exported_at": datetime.now(timezone.utc).isoformat(), "dataset_kind": "synthetic", "tables": {name: len(frame) for name, frame in self.load_bundle().items()}}
        (target / "export_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
