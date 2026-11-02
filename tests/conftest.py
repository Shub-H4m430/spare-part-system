"""
Shared pytest hooks for the Selenium suite.

On any failing test that uses the `driver` fixture, a screenshot and the page
HTML are saved to tests/selenium/artifacts/ (or SPRS_TEST_ARTIFACTS), so a CI
server can archive them as evidence of what the browser actually showed.
"""

import os
import re
from pathlib import Path

import pytest

ARTIFACT_DIR = Path(
    os.environ.get("SPRS_TEST_ARTIFACTS", Path(__file__).resolve().parent / "artifacts")
)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    setattr(item, "rep_" + report.when, report)


@pytest.fixture(autouse=True)
def capture_on_failure(request):
    yield
    report = getattr(request.node, "rep_call", None)
    if report is None or not report.failed or "driver" not in request.fixturenames:
        return
    driver = request.getfixturevalue("driver")
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", request.node.nodeid)
    try:
        driver.save_screenshot(str(ARTIFACT_DIR / (safe_name + ".png")))
        (ARTIFACT_DIR / (safe_name + ".html")).write_text(driver.page_source, encoding="utf-8")
    except Exception as error:  # noqa: BLE001 - never mask the real test failure
        print("Could not save failure artifacts: {}".format(error))
