"""Real Chromium acceptance against a disposable, locally launched Streamlit app."""
from __future__ import annotations

import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.request
import uuid

from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from study_workbench.storage import Storage  # noqa: E402


def run():
    expect.set_options(timeout=30000)
    artifact = ROOT / "artifacts" / "browser"
    artifact.mkdir(parents=True, exist_ok=True)
    # A unique DB means reruns never damage saved user corrections.
    db = ROOT / "data" / "browser" / f"smoke_{uuid.uuid4().hex}.sqlite"
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    env = dict(os.environ, WORKBENCH_DB_PATH=str(db))
    pages, errors = [], []
    with (artifact / "server.log").open("w", encoding="utf-8") as log:
        server = subprocess.Popen([sys.executable, "-m", "streamlit", "run", "legacy_app.py", "--server.address", "127.0.0.1", "--server.port", str(port), "--server.headless", "true", "--browser.gatherUsageStats", "false"], cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        try:
            url = f"http://127.0.0.1:{port}"
            deadline = time.monotonic() + 45
            while True:
                try:
                    with urllib.request.urlopen(url + "/_stcore/health", timeout=2) as response:
                        if response.status == 200:
                            break
                except OSError:
                    if time.monotonic() > deadline or server.poll() is not None:
                        raise RuntimeError("Local Streamlit server did not become healthy")
                    time.sleep(.25)
            with sync_playwright() as runtime:
                browser = runtime.chromium.launch(headless=True)
                context = browser.new_context(viewport={"width": 1440, "height": 1100}, accept_downloads=True)
                page = context.new_page()
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.set_default_timeout(30000)

                def select_widget(label):
                    return page.locator('[data-testid="stSelectbox"]').filter(
                        has=page.get_by_text(label, exact=True)
                    )

                def expect_selected(label, value):
                    expect(select_widget(label).get_by_role("combobox")).to_have_value(str(value))

                def choose(label, value):
                    select_widget(label).get_by_role("combobox").click()
                    page.get_by_role("option", name=value, exact=True).click()
                    expect_selected(label, value)

                def screenshot(name):
                    page.locator('[data-testid="stMain"]').evaluate("el => el.scrollTop = 0")
                    page.screenshot(path=str(artifact / name), full_page=True)

                page.goto(url)
                expect(page.get_by_role("heading", name="Good research starts with reliable records")).to_be_visible()
                page.get_by_role("button", name="Load synthetic demo", exact=True).click()
                expect(page.get_by_role("heading", name="A clear view of study progress")).to_be_visible()
                expect(page.locator('[data-testid="stPlotlyChart"] .js-plotly-plot').first).to_be_visible()
                screenshot("overview.png")
                pages.append("Overview")
                for name in ["Quality review", "Follow-up", "Corrections & audit", "Data dictionary", "Public data", "Reports"]:
                    page.locator('[data-testid="stSidebar"]').get_by_text(name, exact=True).click()
                    expect(page.get_by_role("radio", name=name, exact=True)).to_be_checked()
                    heading = {"Quality review": "Review the evidence behind each finding", "Follow-up": "Plan the next follow-up", "Corrections & audit": "Correct with a reason. Keep the history.", "Data dictionary": "A shared definition for every field", "Public data": "Smoking measures in NHANES", "Reports": "A study brief you can reproduce"}[name]
                    expect(page.get_by_role("heading", name=heading, exact=True)).to_be_visible()
                    expect(page.locator('[data-testid="stException"]')).to_have_count(0)
                    if name == "Quality review":
                        page.get_by_role("tab", name="Injected-error benchmark").click()
                        page.get_by_role("button", name="Run injected-error benchmark").click()
                        expect(page.get_by_text("Known injected defect labels:", exact=False).first).to_be_visible()
                    if name == "Corrections & audit":
                        choose("Table to correct", "baseline")
                        baseline = Storage(db).load_bundle()["baseline"].iloc[0]
                        baseline_row = baseline.row_id
                        expect_selected("Record row ID", baseline_row)
                        choose("Field to correct", "readiness")
                        current = baseline.readiness
                        expect(page.get_by_role("textbox", name="New value", exact=True)).to_have_value(str(current))
                        replacement = "7" if current != 7 else "8"
                        page.get_by_role("textbox", name="New value", exact=True).fill(replacement)
                        page.get_by_role("textbox", name="Reviewer name").fill("Browser acceptance")
                        page.get_by_role("textbox", name="Correction reason").fill("Verified against synthetic source form")
                        expect(page.get_by_role("textbox", name="New value", exact=True)).to_have_value(replacement)
                        page.get_by_role("button", name="Save reasoned correction").click()
                        expect(page.get_by_text("Correction saved", exact=False)).to_be_visible()
                        assert len(Storage(db).audit_log()) == 1
                    if name == "Follow-up":
                        with page.expect_download() as download:
                            page.get_by_role("button", name="Download follow-up queue").click()
                        download.value.save_as(str(artifact / "followup.csv"))
                    if name == "Reports":
                        with page.expect_download() as download:
                            page.get_by_role("button", name="Download one-page HTML report").click()
                        download.value.save_as(str(artifact / "study_report.html"))
                    screenshot(name.lower().replace(" ", "_").replace("&", "and") + ".png")
                    pages.append(name)
                assert not errors, errors
                assert len(Storage(db).audit_log()) == 1
                browser.close()
            result = {"status": "passed", "pages": pages, "page_errors": errors, "persistent_corrections": 1, "downloaded": ["followup.csv", "study_report.html"], "browser": "Chromium", "isolation": "Unique disposable local database; no actual communications"}
            (artifact / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
            print(json.dumps(result, indent=2))
        finally:
            server.terminate()
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait(timeout=5)


if __name__ == "__main__":
    run()
