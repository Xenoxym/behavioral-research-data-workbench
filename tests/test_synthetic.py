import pandas as pd
import pytest
from study_workbench.schema import TABLE_COLUMNS, load_bundle, save_bundle
from study_workbench.synthetic import generate_clean, generate_demo, inject_errors


def test_default_cohort_is_deterministic_and_complete():
    first, second = generate_clean(), generate_clean()
    assert len(first["participants"]) == 240
    assert first["participants"].enrollment_date.notna().sum() == 182
    for table in TABLE_COLUMNS:
        pd.testing.assert_frame_equal(first[table], second[table])
        assert first[table].row_id.is_unique
        assert first[table].participant_id.str.startswith("SYN-").all()
    assert set(first["ema"].response_state) == {"answered", "missed", "declined", "not_applicable"}
    assert first["participants"].withdrawal_date.notna().any()
    assert first["baseline"].nicotine_replacement.eq(1).any()
    assert first["visits"].query("status == 'completed'").co_ppm.isna().any()


@pytest.mark.parametrize("n", [0, -1, True, 2.5])
def test_invalid_cohort_size(n):
    with pytest.raises(ValueError, match="positive integer"):
        generate_clean(n=n)


def test_injection_is_separate_and_leaves_clean_unchanged():
    clean = generate_clean()
    original = {table: frame.copy(deep=True) for table, frame in clean.items()}
    dirty, truth = inject_errors(clean)
    for table in clean:
        pd.testing.assert_frame_equal(clean[table], original[table])
        assert not {"rule_id", "truth", "is_error"} & set(dirty[table].columns)
    assert list(truth.columns) == ["table", "row_id", "field", "rule_id"]
    assert len(truth) == 42
    assert set(truth.table) == set(TABLE_COLUMNS)


def test_demo_csv_roundtrip(tmp_path):
    manifest = generate_demo(tmp_path)
    assert manifest["counts"]["participants"] == 240
    assert manifest["labelled_defects"] == 42
    loaded = load_bundle(manifest["clean_dir"])
    assert loaded["participants"].row_id.iloc[0] == "P0001"
    assert loaded["participants"].participant_id.iloc[0] == "SYN-0001"
    save_bundle(loaded, tmp_path / "copy")
    copied = load_bundle(tmp_path / "copy")
    for table in loaded:
        pd.testing.assert_frame_equal(loaded[table], copied[table])


def test_csv_preserves_literal_na_and_rejects_bad_columns(tmp_path):
    bundle = generate_clean(n=5)
    bundle["contacts"].loc[0, "note"] = "NA"
    save_bundle(bundle, tmp_path)
    assert load_bundle(tmp_path)["contacts"].loc[0, "note"] == "NA"
    bundle["baseline"] = bundle["baseline"].drop(columns="co_ppm")
    with pytest.raises(ValueError, match="Column mismatch"):
        save_bundle(bundle, tmp_path)


def test_injection_small_cohort_fails_explicably():
    with pytest.raises(ValueError, match="30 nonwithdrawn"):
        inject_errors(generate_clean(n=10))
