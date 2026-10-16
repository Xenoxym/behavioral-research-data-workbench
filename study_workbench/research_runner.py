"""Reproduce real-data research with an explicit, authoritative survey-analysis engine."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
TABLES = ("estimates.csv", "contrasts.csv", "models.csv", "sensitivities.csv", "missingness.csv")


def digest(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def find_rscript(explicit: str | Path | None = None) -> Path:
    """Resolve a caller-selected, project-local, or existing PATH runtime, in that order."""
    selected = explicit or os.environ.get("RESEARCH_RSCRIPT")
    if selected:
        resolved = Path(selected).expanduser().resolve()
        if not resolved.is_file():
            raise FileNotFoundError(f"Rscript not found: {resolved}")
        return resolved
    for candidate in (ROOT / ".tools/R/bin/Rscript.exe", ROOT / ".tools/R/bin/Rscript"):
        if candidate.is_file():
            return candidate.resolve()
    installed = shutil.which("Rscript")
    if installed:
        return Path(installed).resolve()
    raise FileNotFoundError(
        "Rscript is required for survey-weighted inference. On Windows run "
        "powershell -ExecutionPolicy Bypass -File scripts/setup_research_r.ps1; "
        "otherwise install R with survey/jsonlite. Set RESEARCH_RSCRIPT if necessary."
    )


def run_r(script: str | Path, arguments: list[str | Path], rscript=None) -> dict:
    runtime = find_rscript(rscript)
    env = os.environ.copy()
    env.update(LC_ALL="C", LANG="C", OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1")
    local_library = ROOT / ".tools/R-library"
    if local_library.exists():
        env["R_LIBS_USER"] = str(local_library)
    completed = subprocess.run(
        [str(runtime), "--vanilla", str(Path(script).resolve()), *map(str, arguments)],
        cwd=ROOT, env=env, text=True, encoding="utf-8", errors="replace",
        capture_output=True, timeout=1200, check=False,
    )
    if completed.returncode:
        raise RuntimeError(
            f"Survey analysis failed (exit {completed.returncode}).\n"
            f"{completed.stdout[-6000:]}\n{completed.stderr[-6000:]}"
        )
    return {"stdout": completed.stdout, "stderr": completed.stderr}


def run_research(cache_dir="data/research/raw", work_dir="data/research",
                 output_dir="reports/research", *, offline=False, prepare_only=False,
                 rscript=None) -> dict:
    from .research_data import prepare_research

    output = Path(output_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    paths = prepare_research(cache_dir=cache_dir, work_dir=work_dir,
                             output_dir=output, offline=offline)
    if prepare_only:
        return {"status": "data_prepared_only", **paths}
    # Stage the inference outputs, so a failed engine never overwrites prior estimates.
    with tempfile.TemporaryDirectory(prefix="survey-", dir=Path(work_dir).resolve()) as temp:
        stage = Path(temp)
        engine_log = run_r(ROOT / "research/analysis.R", [paths["analytic_path"], stage], rscript)
        required = (*TABLES, "analysis_metadata.json")
        absent = [name for name in required if not (stage / name).is_file()]
        if absent:
            raise RuntimeError(f"Incomplete survey outputs: {absent}")
        for name in required:
            shutil.copyfile(stage / name, output / name)
    (output / "engine.log").write_text(
        engine_log["stdout"] + "\n" + engine_log["stderr"], encoding="utf-8")
    from .research_reporting import build_research_report

    build_research_report(output)
    code_files = ("research/analysis.R", "study_workbench/research_data.py",
                  "study_workbench/research_runner.py", "study_workbench/research_reporting.py",
                  "docs/RESEARCH_PLAN_V2.md")
    evidence = {
        "completed_at_utc": datetime.now(timezone.utc).isoformat(),
        "kind": "real CDC public records; independent secondary analysis",
        "offline": offline,
        "analytic_sha256": digest(paths["analytic_path"]),
        "source_manifest_sha256": digest(output / "source_manifest.json"),
        "code_sha256": {name: digest(ROOT / name) for name in code_files},
        "output_sha256": {name: digest(output / name) for name in required},
        "engine_warnings_file": "engine.log",
    }
    (output / "pipeline_run.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    return {"status": "completed", **paths, "report": str(output.parent / "RESEARCH_REPORT.html"),
            "evidence": str(output / "pipeline_run.json")}
