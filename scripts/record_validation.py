"""Capture completed local/browser and remote CI evidence, without inventing results."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ci-run", required=True)
    args = parser.parse_args()
    junit = ROOT / "artifacts" / "junit.xml"
    suites = ET.parse(junit).getroot().findall(".//testsuite")
    counts = {key: sum(int(s.attrib.get(key, 0)) for s in suites) for key in ["tests", "failures", "errors", "skipped"]}
    if counts["failures"] or counts["errors"] or not counts["tests"]:
        raise RuntimeError("A passing actual JUnit result is required")
    browser = json.loads((ROOT / "artifacts" / "browser" / "result.json").read_text(encoding="utf-8"))
    if browser["status"] != "passed":
        raise RuntimeError("A passing actual browser result is required")
    ci = json.loads(subprocess.check_output(["gh", "run", "view", args.ci_run, "--json", "status,conclusion,headSha,url,jobs"], cwd=ROOT, text=True, encoding="utf-8"))
    if ci["status"] != "completed" or ci["conclusion"] != "success":
        raise RuntimeError("Completed successful CI is required")
    source = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    if ci["headSha"] != source:
        raise RuntimeError("CI must validate the current source commit")
    result = {
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
        "validated_source_commit": source,
        "local_pytest": {**counts, "seconds": sum(float(s.attrib.get("time", 0)) for s in suites), "junit_sha256": hashlib.sha256(junit.read_bytes()).hexdigest()},
        "browser": browser,
        "ci": {"url": ci["url"], "status": ci["status"], "conclusion": ci["conclusion"], "head_sha": ci["headSha"], "jobs": [{"name": job["name"], "conclusion": job["conclusion"], "url": job["url"]} for job in ci["jobs"]]},
        "interpretation": "Finite software acceptance and synthetic defect evaluation, not clinical validation or real participant experience.",
    }
    (ROOT / "reports" / "validation.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
