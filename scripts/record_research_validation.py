"""Record actual V2 local and remote acceptance, with explicit source identities."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]


def _run(run_id):
    return json.loads(subprocess.check_output(
        ["gh", "run", "view", str(run_id), "--json", "status,conclusion,headSha,url,jobs"],
        cwd=ROOT, text=True, encoding="utf-8"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ci-run", required=True)
    parser.add_argument("--reproduction-run", required=True)
    args = parser.parse_args()
    suites = ET.parse(ROOT / "artifacts/junit_v2.xml").getroot().findall(".//testsuite")
    counts = {name: sum(int(s.attrib.get(name, 0)) for s in suites)
              for name in ("tests", "failures", "errors", "skipped")}
    if not counts["tests"] or any(counts[k] for k in ("failures", "errors", "skipped")):
        raise RuntimeError("Actual complete local acceptance without failures/skips is required")
    ci, reproduction = _run(args.ci_run), _run(args.reproduction_run)
    source = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    for run in (ci, reproduction):
        if run["status"] != "completed" or run["conclusion"] != "success" or run["headSha"] != source:
            raise RuntimeError("Both successful remote workflows must validate current source HEAD")
    browser = json.loads((ROOT / "reports/research_browser_validation.json").read_text(encoding="utf-8"))
    replay = json.loads((ROOT / "reports/research/replay_validation.json").read_text(encoding="utf-8"))
    if browser["status"] != "passed" or replay["status"] != "passed":
        raise RuntimeError("Actual browser and full offline replay must pass")
    result = {
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
        "validated_source_commit": source, "local_pytest": counts,
        "local_seconds": sum(float(s.attrib.get("time", 0)) for s in suites),
        "browser": browser, "offline_replay": replay,
        "ci": {k: ci[k] for k in ("url", "conclusion", "headSha", "jobs")},
        "full_real_data_reproduction": {k: reproduction[k] for k in ("url", "conclusion", "headSha", "jobs")},
        "scope": "Software/statistical consistency and reproducibility; not clinical validation or proof of absence of observational bias.",
    }
    (ROOT / "reports/research_validation.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
