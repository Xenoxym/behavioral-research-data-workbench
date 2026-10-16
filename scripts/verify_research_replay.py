"""Re-run the complete real-data pipeline offline and compare scientific outputs exactly."""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

from study_workbench.research_runner import TABLES, digest, run_research

ROOT = Path(__file__).resolve().parents[1]


def main():
    saved = ROOT / "reports/research"
    original = json.loads((saved / "source_manifest.json").read_text(encoding="utf-8"))
    expected = {name: digest(saved / name) for name in TABLES}
    repeat = ROOT / "artifacts/offline_replay/research"
    run_research(cache_dir=ROOT / "data/research/raw", work_dir=ROOT / "artifacts/offline_replay/data",
                 output_dir=repeat, offline=True)
    replay = json.loads((repeat / "source_manifest.json").read_text(encoding="utf-8"))
    checks = {name: digest(repeat / name) == checksum for name, checksum in expected.items()}
    same_input = original["analytic_csv_sha256"] == replay["analytic_csv_sha256"]
    def provenance(manifest):
        return {s["name"]: (s["sha256"], s["retrieved_at_utc"]) for s in manifest["sources"]}
    same_sources = provenance(original) == provenance(replay)
    result = {
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "passed" if all(checks.values()) and same_input and same_sources else "failed",
        "mode": "full validated-cache preparation + R survey inference + report, offline=True",
        "analytic_input_identical": same_input, "source_bytes_and_retrieval_times_preserved": same_sources,
        "scientific_tables_identical": checks, "scientific_table_sha256": expected,
        "excluded_from_byte_comparison": "Generated timestamps, run metadata and rendered figures; scientific CSVs compared exactly.",
    }
    (saved / "replay_validation.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    if result["status"] != "passed":
        raise SystemExit("Offline scientific reproducibility check failed")


if __name__ == "__main__":
    main()
