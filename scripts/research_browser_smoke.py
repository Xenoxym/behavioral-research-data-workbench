"""Chromium acceptance using saved real research outputs; never generates demo data."""

from __future__ import annotations

import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.request

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from study_workbench.research_ui import PAGES, load_artifacts  # noqa: E402

HEADINGS = {
    "Study overview": "Tobacco exposure and the income gradient",
    "Questions & methods": "Define the study before interpreting it",
    "Weighted results": "Explore the weighted results and uncertainty",
    "Sensitivity & selection": "Check what changes when the definition changes",
    "Sources & provenance": "Trace every result back to its source",
    "Research report": "Read the findings with their limitations",
}


def run() -> None:
    expect.set_options(timeout=30000)
    directory = Path(os.environ.get("WORKBENCH_RESEARCH_DIR", str(ROOT / "reports" / "research")))
    report = Path(os.environ.get("WORKBENCH_RESEARCH_REPORT", str(ROOT / "reports" / "RESEARCH_REPORT.html")))
    state = load_artifacts(directory)
    if state["errors"]:
        raise RuntimeError("Complete real research artifacts before browser acceptance: " + "; ".join(state["errors"]))
    if not report.exists():
        raise RuntimeError("Complete the real research HTML report before browser acceptance")
    estimates = state["tables"]["estimates"]
    if set(estimates["period"].astype(str)) != {"I", "P", "L"}:
        raise RuntimeError("Expected all three saved, non-overlapping real survey periods")
    artifact = ROOT / "artifacts" / "research_browser"
    artifact.mkdir(parents=True, exist_ok=True)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    env = dict(os.environ, WORKBENCH_RESEARCH_DIR=str(directory), WORKBENCH_RESEARCH_REPORT=str(report))
    errors, console_errors, request_failures, visited, downloaded = [], [], [], [], []
    with (artifact / "server.log").open("w", encoding="utf-8") as log:
        server = subprocess.Popen(
            [sys.executable, "-m", "streamlit", "run", "app.py", "--server.address", "127.0.0.1",
             "--server.port", str(port), "--server.headless", "true", "--browser.gatherUsageStats", "false"],
            cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
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
                        raise RuntimeError("Own local Streamlit server did not become healthy")
                    time.sleep(.25)
            with sync_playwright() as runtime:
                browser = runtime.chromium.launch(
                    headless=True,
                    args=["--disable-gpu", "--disable-software-rasterizer", "--renderer-process-limit=1"],
                )
                context = browser.new_context(viewport={"width": 1440, "height": 1100}, accept_downloads=True)
                page = context.new_page()
                page.set_default_timeout(30000)
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.on("console", lambda message: console_errors.append(message.text) if message.type == "error" else None)
                page.on("requestfailed", lambda request: request_failures.append({"url": request.url, "failure": request.failure}))

                def download(label, filename):
                    with page.expect_download() as event:
                        page.get_by_role("button", name=label, exact=True).click()
                    event.value.save_as(str(artifact / filename))
                    assert (artifact / filename).stat().st_size > 0
                    downloaded.append(filename)

                try:
                    page.goto(url)
                    for name in PAGES:
                        if name != PAGES[0]:
                            page.locator('[data-testid="stSidebar"]').get_by_text(name, exact=True).click()
                        expect(page.get_by_role("radio", name=name, exact=True)).to_be_checked()
                        expect(page.get_by_role("heading", name=HEADINGS[name], exact=True)).to_be_visible()
                        expect(page.locator('[data-testid="stException"]')).to_have_count(0)
                        expect(page.get_by_role("button", name="Load synthetic demo", exact=True)).to_have_count(0)
                        if name in {"Study overview", "Weighted results", "Sensitivity & selection"}:
                            expect(page.locator('[data-testid="stPlotlyChart"] .js-plotly-plot').first).to_be_visible()
                        if name == "Weighted results":
                            select = page.get_by_role("combobox", name="Compare by", exact=True)
                            select.click()
                            page.get_by_role("option", name="Educational attainment", exact=True).click()
                            expect(select).to_have_value("Educational attainment")
                            expect(page.get_by_role("combobox", name="Subgroups", exact=True)).to_be_visible()
                            download("Download selected weighted estimates", "selected_weighted_estimates.csv")
                        elif name == "Sensitivity & selection":
                            download("Download missingness CSV", "missingness.csv")
                        elif name == "Sources & provenance":
                            download("Download research evidence ZIP", "research_evidence.zip")
                        elif name == "Research report":
                            expect(page.locator("iframe")).to_have_count(1)
                            expect(page.frame_locator("iframe").locator("body")).to_contain_text("NHANES")
                            download("Download research report HTML", "RESEARCH_REPORT.html")
                        page.locator('[data-testid="stMain"]').evaluate("el => el.scrollTop = 0")
                        filename = name.lower().replace(" & ", "_").replace(" ", "_") + ".png"
                        page.screenshot(path=str(artifact / filename), full_page=True)
                        visited.append(name)
                    assert not errors, errors
                    assert not console_errors, console_errors
                except Exception:
                    page.screenshot(path=str(artifact / "failure.png"), full_page=True)
                    (artifact / "failure_dom.html").write_text(page.content(), encoding="utf-8")
                    failure = {"page_errors": errors, "console_errors": console_errors, "request_failures": request_failures, "visited": visited}
                    (artifact / "failure.json").write_text(json.dumps(failure, indent=2), encoding="utf-8")
                    print(json.dumps(failure, indent=2))
                    raise
                finally:
                    context.close()
                    browser.close()
            result = {
                "status": "passed", "app": "Real-data Tobacco Exposure Equity Study", "pages": visited,
                "page_errors": errors, "console_errors": console_errors, "downloaded": downloaded,
                "browser": "Chromium", "real_periods": sorted(estimates["period"].astype(str).unique()),
                "isolation": "Read-only saved aggregate artifacts; own local server; no source download or synthetic generation",
            }
            (artifact / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
            print(json.dumps(result, indent=2))
        except Exception as exc:
            diagnostics = " ".join([str(exc), *errors, *console_errors])
            resource_limited = any(marker in diagnostics.lower() for marker in [
                "err_insufficient_resources", "failed to start browserthread", "out of memory",
            ])
            result = {
                "status": "blocked_environment" if resource_limited else "failed",
                "pages": visited, "page_errors": errors, "console_errors": console_errors,
                "downloaded": downloaded, "browser": "Chromium",
                "reason": str(exc)[:1500],
            }
            (artifact / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
            raise
        finally:
            server.terminate()
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait(timeout=5)


if __name__ == "__main__":
    run()
