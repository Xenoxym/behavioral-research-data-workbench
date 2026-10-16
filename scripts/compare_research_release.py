"""Compare a fresh computation with the committed release, allowing floating-point noise."""
from __future__ import annotations

from io import BytesIO
import json
from pathlib import Path
import subprocess

import numpy as np
import pandas as pd

from study_workbench.research_runner import TABLES

ROOT = Path(__file__).resolve().parents[1]


def committed(path):
    return subprocess.check_output(["git", "show", "HEAD:" + path], cwd=ROOT)


def main():
    checks = {}
    for name in TABLES:
        previous = pd.read_csv(BytesIO(committed("reports/research/" + name)))
        current = pd.read_csv(ROOT / "reports/research" / name)
        if list(previous.columns) != list(current.columns) or previous.shape != current.shape:
            raise AssertionError(f"Changed scientific table structure: {name}")
        for column in previous:
            if pd.api.types.is_numeric_dtype(previous[column]) and not pd.api.types.is_bool_dtype(previous[column]):
                np.testing.assert_allclose(previous[column], current[column], rtol=1e-9,
                                           atol=1e-11, equal_nan=True, err_msg=f"{name}:{column}")
            else:
                pd.testing.assert_series_equal(previous[column].fillna(""), current[column].fillna(""),
                                               check_names=False)
        checks[name] = {"matched": True, "rows": len(current), "columns": len(current.columns)}
    old_manifest = json.loads(committed("reports/research/source_manifest.json"))
    new_manifest = json.loads((ROOT / "reports/research/source_manifest.json").read_text(encoding="utf-8"))
    original = {s["name"]: s["sha256"] for s in old_manifest["sources"]}
    fresh = {s["name"]: s["sha256"] for s in new_manifest["sources"]}
    if original != fresh:
        raise AssertionError("Official source bytes changed since committed research release")
    result = {"status": "passed", "reference": "committed Git HEAD scientific tables and source checksums",
              "source_count": len(fresh), "all_source_bytes_identical": True,
              "numeric_tolerance": {"relative": 1e-9, "absolute": 1e-11}, "tables": checks}
    (ROOT / "reports/research/cross_platform_validation.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
