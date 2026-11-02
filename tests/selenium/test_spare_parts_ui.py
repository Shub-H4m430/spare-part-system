"""
End-to-end UI tests for the Spare Parts Request System (SPRS).

Target server
-------------
* If SPRS_BASE_URL is set (for example http://localhost:5000), the tests run
  against that already-running server. The Jenkins pipeline uses this mode.
* Otherwise the suite starts its own copy of src/app.py on a free port with a
  temporary data file, so local runs never touch your real data.json.

Browser and driver
------------------
Chrome runs headless by default (set SPRS_TEST_HEADLESS=0 to watch it).
The ChromeDriver is resolved in this order:
  1. CHROMEDRIVER_PATH, if set
  2. webdriver-manager (downloads a matching driver, needs internet)
  3. Selenium Manager, built into Selenium 4.6+
CHROME_BIN can point to a specific Chrome or Chromium binary.

Credentials
-----------
SPRS_TEST_WORKER_USER / SPRS_TEST_WORKER_PASSWORD / SPRS_TEST_WORKER_NAME
default to the seeded worker account "ravi".
"""

import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

import pytest
from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

PROJECT_ROOT = Path(__file__).resolve().parents[2]
APP_PATH = PROJECT_ROOT / "src" / "app.py"

WORKER_USER = os.environ.get("SPRS_TEST_WORKER_USER", "ravi")
WORKER_PASSWORD = os.environ.get("SPRS_TEST_WORKER_PASSWORD", "Ravi@2026")
WORKER_NAME = os.environ.get("SPRS_TEST_WORKER_NAME", "Ravi Patil")

HEADLESS = os.environ.get("SPRS_TEST_HEADLESS", "1") != "0"
WAIT_SECONDS = int(os.environ.get("SPRS_TEST_TIMEOUT", "15"))
SERVER_START_SECONDS = int(os.environ.get("SPRS_TEST_SERVER_TIMEOUT", "30"))


# --------------------------------------------------------------------------
# Server helpers
# --------------------------------------------------------------------------
def _is_sprs_healthy(base_url):
    """True only if base_url answers /health with SPRS's own JSON payload."""
    try:
        with urllib.request.urlopen(base_url.rstrip("/") + "/health", timeout=2) as resp:
            return resp.status == 200 and json.load(resp).get("status") == "ok"
    except (urllib.error.URLError, ValueError, OSError):
        return False


def _wait_until_healthy(base_url, seconds, process=None):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if process is not None and process.poll() is not None:
            return False
        if _is_sprs_healthy(base_url):
            return True
        time.sleep(0.5)
    return False


def _free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture(scope="session")
def base_url():
    """URL of a running SPRS instance, started by the suite if necessary."""
    external = os.environ.get("SPRS_BASE_URL", "").strip().rstrip("/")
    if external:
        if not _wait_until_healthy(external, SERVER_START_SECONDS):
            pytest.fail(
                "SPRS_BASE_URL={} is set but {}/health did not report status ok "
                "within {}s.".format(external, external, SERVER_START_SECONDS)
            )
        yield external
        return

    work_dir = tempfile.mkdtemp(prefix="sprs-ui-")
    port = _free_port()
    log_path = os.path.join(work_dir, "server.log")
    env = dict(
        os.environ,
        SPRS_HOST="127.0.0.1",
        SPRS_PORT=str(port),
        SPRS_DATA_FILE=os.path.join(work_dir, "data.json"),
        SPRS_DEMO_MODE="0",
        SPRS_DEBUG="0",
    )
    log_file = open(log_path, "w", encoding="utf-8")
    process = subprocess.Popen(
        [sys.executable, str(APP_PATH)],
        cwd=str(PROJECT_ROOT),
        env=env,
        stdout=log_file,
        stderr=subprocess.STDOUT,
    )
    url = "http://127.0.0.1:{}".format(port)
    try:
        if not _wait_until_healthy(url, SERVER_START_SECONDS, process):
            log_file.flush()
            with open(log_path, encoding="utf-8") as fh:
                output = fh.read()
            pytest.fail("Could not start SPRS for the UI tests. Server output:\n" + output)
        yield url
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
        log_file.close()


# --------------------------------------------------------------------------
# Browser helpers
# --------------------------------------------------------------------------
def _chrome_options():
    options = Options()
    if HEADLESS:
        options.add_argument("--headless=new")
    options.add_argument("--window-size=1366,900")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-extensions")
    chrome_bin = os.environ.get("CHROME_BIN")
    if chrome_bin:
        options.binary_location = chrome_bin
    return options


def _start_chrome():
    options = _chrome_options()

    driver_path = os.environ.get("CHROMEDRIVER_PATH")
    if driver_path:
        return webdriver.Chrome(service=Service(driver_path), options=options)

    try:
        from webdriver_manager.chrome import ChromeDriverManager

        return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    except Exception as wdm_error:  # noqa: BLE001 - any failure falls back to Selenium Manager
        print("webdriver-manager could not provide a driver ({}). "
              "Falling back to Selenium Manager.".format(wdm_error))
        return webdriver.Chrome(options=options)


@pytest.fixture(scope="module")
def driver():
    browser = _start_chrome()
    browser.implicitly_wait(0)
    yield browser
    browser.quit()


def wait_for(driver, condition):
    return WebDriverWait(driver, WAIT_SECONDS).until(condition)


def sign_in_as_worker(driver, base_url):
    """Start a clean session and sign in through the real login form."""
    driver.delete_all_cookies()
    driver.get(base_url + "/login")
    wait_for(driver, EC.visibility_of_element_located((By.ID, "username"))).send_keys(WORKER_USER)
    driver.find_element(By.ID, "password").send_keys(WORKER_PASSWORD)
    driver.find_element(By.ID, "btn-login").click()
    try:
        wait_for(driver, EC.presence_of_element_located((By.ID, "user-chip")))
    except TimeoutException:
        pytest.fail("Sign-in as '{}' failed. Page said: {}".format(
            WORKER_USER, driver.find_element(By.TAG_NAME, "body").text[:300]))


def open_as_worker(driver, base_url, path):
    """Open a page, signing in first if the session has expired or is missing."""
    driver.get(base_url + path)
    if "/login" in driver.current_url:
        sign_in_as_worker(driver, base_url)
        driver.get(base_url + path)


def fill_request_form(driver, values):
    """Fill the full-page submission form. Requester is not a field: it comes from the session."""
    for field_id in ("part_name", "part_number", "quantity", "asset_id", "justification"):
        element = wait_for(driver, EC.visibility_of_element_located((By.ID, field_id)))
        element.clear()
        element.send_keys(values[field_id])
    # The urgency radios are visually hidden Bootstrap "btn-check" inputs, so click the label.
    driver.find_element(By.CSS_SELECTOR, "label[for='urg_{}']".format(values["urgency"])).click()


@pytest.fixture(scope="module")
def submitted_request(driver, base_url):
    """
    Submit one request through the UI and capture everything the tests need.
    Values are unique per run, so repeated runs and the duplicate check never collide.
    """
    suffix = uuid.uuid4().hex[:6].upper()
    values = {
        "part_name": "Selenium Test Bearing {}".format(suffix),
        "part_number": "SEL-{}-6205".format(suffix),
        "quantity": "3",
        "urgency": "High",
        "asset_id": "TEST-CNC-{}".format(suffix),
        "justification": "Automated UI test {}: spindle bearing vibration above limit.".format(suffix),
    }

    sign_in_as_worker(driver, base_url)
    driver.get(base_url + "/submit")
    requester_display = wait_for(
        driver, EC.visibility_of_element_located((By.ID, "requester-display"))
    ).text
    fill_request_form(driver, values)
    driver.find_element(By.ID, "btn-submit").click()

    wait_for(driver, EC.url_matches(r"/status/SPR-\d{4}$"))
    flash = wait_for(
        driver, EC.visibility_of_element_located((By.CSS_SELECTOR, "[data-flash='success']"))
    ).text
    request_id = re.search(r"(SPR-\d{4})$", driver.current_url).group(1)

    return {
        "id": request_id,
        "values": values,
        "requester_display": requester_display,
        "status_url": driver.current_url,
        "flash": flash,
        "heading": driver.find_element(By.TAG_NAME, "h1").text,
        "status_badges": [
            badge.get_attribute("data-status")
            for badge in driver.find_elements(By.CSS_SELECTOR, ".panel-head [data-status]")
        ],
        "latest_event": driver.find_element(By.CSS_SELECTOR, "#timeline li").text,
    }


# --------------------------------------------------------------------------
# 1. Homepage: title and header elements
# --------------------------------------------------------------------------
def test_homepage_requires_sign_in(driver, base_url):
    driver.delete_all_cookies()
    driver.get(base_url + "/")

    wait_for(driver, EC.url_contains("/login"))
    assert driver.title == "Sign In · SPRS"
    assert driver.find_element(By.TAG_NAME, "h1").text == "Sign in to SPRS"
    assert "Please sign in to continue." in driver.find_element(By.CSS_SELECTOR, "[data-flash]").text


def test_homepage_loads_with_title_and_header(driver, base_url):
    sign_in_as_worker(driver, base_url)
    driver.get(base_url + "/")

    assert driver.title == "Dashboard · SPRS"

    brand = driver.find_element(By.CSS_SELECTOR, ".navbar-brand")
    assert "SPRS" in brand.text
    assert "SPARE PARTS REQUEST SYSTEM" in brand.text.upper()

    heading = driver.find_element(By.TAG_NAME, "h1").text
    assert heading == "My Spare Parts Requests"

    user_chip = driver.find_element(By.ID, "user-chip")
    assert WORKER_NAME in user_chip.text
    assert user_chip.find_element(By.CSS_SELECTOR, "[data-role]").get_attribute("data-role") == "worker"

    nav_links = [link.text for link in driver.find_elements(By.CSS_SELECTOR, "#mainNav .nav-link")]
    assert "My Requests" in nav_links
    assert "New Request" in nav_links
    assert "Awaiting Approval" not in nav_links, "worker must not see manager navigation"

    assert driver.find_element(By.ID, "kpi-strip").get_attribute("data-scope") == "own"
    assert driver.find_element(By.ID, "btn-open-submit").is_displayed()


# --------------------------------------------------------------------------
# 2. Submitting a new request
# --------------------------------------------------------------------------
def test_submit_request_redirects_with_success_flash(submitted_request):
    request_id = submitted_request["id"]

    assert re.search(r"/status/SPR-\d{4}$", submitted_request["status_url"])
    assert submitted_request["flash"].startswith(
        "Request {} submitted successfully.".format(request_id)
    )
    assert request_id in submitted_request["heading"]
    assert submitted_request["status_badges"][0] == "Pending"

    # Requester is not typed: it is locked to the signed-in worker.
    assert WORKER_NAME in submitted_request["requester_display"]
    assert "@" + WORKER_USER in submitted_request["requester_display"]

    latest = submitted_request["latest_event"]
    assert "Request submitted." in latest
    assert WORKER_NAME in latest


# --------------------------------------------------------------------------
# 3. The new request appears in the dashboard table
# --------------------------------------------------------------------------
def test_new_request_appears_in_dashboard_table(driver, base_url, submitted_request):
    request_id = submitted_request["id"]
    values = submitted_request["values"]

    open_as_worker(driver, base_url, "/")
    row = wait_for(
        driver,
        EC.presence_of_element_located(
            (By.CSS_SELECTOR, "#requests-table tr[data-request-id='{}']".format(request_id))
        ),
    )
    cells = row.find_elements(By.TAG_NAME, "td")

    assert cells[0].text == request_id
    assert values["part_name"] in cells[1].text
    assert values["part_number"] in cells[1].text
    assert cells[2].text == values["quantity"]
    assert cells[3].text == values["asset_id"]
    assert values["urgency"] in cells[4].text
    assert cells[5].find_element(By.CSS_SELECTOR, "[data-status]").get_attribute("data-status") == "Pending"

    # Searching by the unique part number must return exactly this row.
    search = driver.find_element(By.ID, "f-q")
    search.clear()
    search.send_keys(values["part_number"])
    driver.find_element(By.CSS_SELECTOR, "#filter-form button[type='submit']").click()
    wait_for(driver, EC.url_contains("q="))
    rows = driver.find_elements(By.CSS_SELECTOR, "#requests-table tbody tr")
    assert [r.get_attribute("data-request-id") for r in rows] == [request_id]


# --------------------------------------------------------------------------
# Additional guards
# --------------------------------------------------------------------------
def test_invalid_submission_shows_field_error(driver, base_url):
    open_as_worker(driver, base_url, "/submit")
    fill_request_form(
        driver,
        {
            "part_name": "Invalid Quantity Check",
            "part_number": "SEL-INVALID-01",
            "quantity": "0",
            "urgency": "Low",
            "asset_id": "TEST-INVALID",
            "justification": "This request must be refused because quantity is zero.",
        },
    )
    driver.find_element(By.ID, "btn-submit").click()

    error = wait_for(
        driver, EC.visibility_of_element_located((By.CSS_SELECTOR, "[data-error-for='quantity']"))
    )
    assert "Quantity must be a whole number from 1 to 10000." in error.text
    assert driver.current_url.endswith("/submit")
    assert driver.find_element(By.CSS_SELECTOR, "[data-flash='danger']").is_displayed()
    assert driver.find_element(By.ID, "part_name").get_attribute("value") == "Invalid Quantity Check"


def test_worker_cannot_open_manager_review_page(driver, base_url, submitted_request):
    open_as_worker(driver, base_url, "/review/" + submitted_request["id"])

    assert driver.find_element(By.TAG_NAME, "h1").text == "Error 403"
    assert "only available to managers" in driver.find_element(By.TAG_NAME, "body").text
    assert not driver.find_elements(By.ID, "btn-approve")
