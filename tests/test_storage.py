import sqlite3

import pytest

from study_workbench.storage import Storage
from study_workbench.synthetic import generate_clean
from study_workbench.schema import load_bundle, save_bundle


def test_persistence_raw_preservation_idempotency_and_export(tmp_path):
    bundle = generate_clean()
    path = tmp_path / "work.sqlite"
    store = Storage(path)
    imported = store.import_bundle(bundle)
    assert imported["inserted"] == sum(map(len, bundle.values()))
    first = bundle["baseline"].iloc[0]
    store.correct("baseline", first.row_id, "readiness", 6 if first.readiness != 6 else 7, "Verified against simulated source form", "reviewer")
    assert store.import_bundle(bundle)["inserted"] == 0
    fresh = Storage(path)
    assert len(fresh.audit_log()) == 1
    assert fresh.load_bundle(raw=True)["baseline"].set_index("row_id").loc[first.row_id, "readiness"] == first.readiness
    assert fresh.load_bundle()["baseline"].set_index("row_id").loc[first.row_id, "readiness"] != first.readiness
    fresh.export_bundle(tmp_path / "export")
    assert len(load_bundle(tmp_path / "export")["baseline"]) == len(bundle["baseline"])
    assert (tmp_path / "export" / "audit_log.csv").exists()
    assert (tmp_path / "export" / "export_manifest.json").exists()


def test_conflicting_import_rolls_back_whole_transaction(tmp_path):
    bundle = generate_clean()
    store = Storage(tmp_path / "work.sqlite")
    store.import_bundle(bundle)
    modified = {k: v.copy() for k, v in bundle.items()}
    modified["baseline"].loc[0, "readiness"] = 999
    with pytest.raises(ValueError, match="Conflicting"):
        store.import_bundle(modified)
    assert len(store.audit_log()) == 0
    assert store.load_bundle()["baseline"].iloc[0]["readiness"] != 999


def test_csv_and_in_memory_imports_have_same_identity(tmp_path):
    bundle = generate_clean()
    save_bundle(bundle, tmp_path / "csv")
    store = Storage(tmp_path / "work.sqlite")
    store.import_bundle(load_bundle(tmp_path / "csv"))
    assert store.import_bundle(bundle)["inserted"] == 0


def test_connections_close_and_database_can_be_moved_after_operations(tmp_path):
    store = Storage(tmp_path / "work.sqlite")
    store.import_bundle(generate_clean(n=10))
    store.load_bundle()
    with store._connection() as connection:
        connection.execute("SELECT 1")
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        connection.execute("SELECT 1")
    store.path.rename(tmp_path / "moved.sqlite")


@pytest.mark.parametrize("field,value,reason,actor", [("row_id", "Bother", "x", "y"), ("readiness", "NaN", "x", "y"), ("readiness", 11, "x", "y"), ("readiness", 1.5, "x", "y"), ("nicotine_replacement", 2, "x", "y"), ("readiness", 3, "", "y"), ("readiness", 3, "x", "")])
def test_invalid_correction_is_atomic(tmp_path, field, value, reason, actor):
    bundle = generate_clean()
    store = Storage(tmp_path / "work.sqlite")
    store.import_bundle(bundle)
    with pytest.raises(ValueError):
        store.correct("baseline", bundle["baseline"].iloc[0].row_id, field, value, reason, actor)
    assert store.audit_log().empty


def test_audit_and_raw_records_cannot_be_updated_or_deleted(tmp_path):
    bundle = generate_clean()
    store = Storage(tmp_path / "work.sqlite")
    store.import_bundle(bundle)
    row = bundle["baseline"].iloc[0]
    store.correct("baseline", row.row_id, "readiness", 5 if row.readiness != 5 else 4, "verified", "tester")
    for table in ["raw_records", "audit"]:
        with sqlite3.connect(store.path) as conn:
            with pytest.raises(sqlite3.IntegrityError, match="immutable"):
                conn.execute(f"DELETE FROM {table}")


def test_timestamp_requires_timezone_and_rollback_on_invalid_dates(tmp_path):
    bundle = generate_clean()
    store = Storage(tmp_path / "work.sqlite")
    store.import_bundle(bundle)
    with pytest.raises(ValueError, match="offset"):
        store.correct("ema", bundle["ema"].iloc[0].row_id, "prompted_at", "2026-01-01T10:00:00", "x", "tester")
    with pytest.raises(ValueError, match="date"):
        store.correct("participants", bundle["participants"].iloc[0].row_id, "screening_date", "not-a-date", "x", "tester")
    assert store.audit_log().empty
