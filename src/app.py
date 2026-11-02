"""
Spare Parts Request System (SPRS)
Flask application with JSON-file persistence.

Lifecycle:  Pending -> Validated -> Approved
                    |-> Rejected (from Pending or Validated)

Roles:
  worker   - raises requests, sees and tracks only their own requests
  manager  - sees all requests, runs validation, approves or rejects

Add a user: run `python src/app.py hash-password`, then paste the printed
hash into USERS below. Plaintext passwords are never stored in this file.
"""

import getpass
import hmac
import json
import os
import re
import secrets
import sys
import tempfile
import threading
from datetime import datetime, timedelta
from functools import wraps

from flask import (
    Flask,
    abort,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DATA_FILE = os.environ.get(
    "SPRS_DATA_FILE", os.path.join(BASE_DIR, "data.json")
)

URGENCY_LEVELS = ["Low", "Medium", "High", "Critical"]
STATUSES = ["Pending", "Validated", "Approved", "Rejected"]
OPEN_STATUSES = {"Pending", "Validated"}

PART_NUMBER_RE = re.compile(r"^[A-Z0-9][A-Z0-9\-./]{2,29}$")
ASSET_ID_RE = re.compile(r"^[A-Z0-9][A-Z0-9\-_]{1,19}$")
PERSON_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z .'\-]{1,59}$")

MAX_QUANTITY = 10000
BULK_QUANTITY_THRESHOLD = 100

ROLE_WORKER = "worker"
ROLE_MANAGER = "manager"

# Accounts offered as one-click buttons on the login page, ONLY in demo mode.
# Demo mode is off by default. Turn it on with `python src/app.py --demo`
# or the environment variable SPRS_DEMO_MODE=1.
DEMO_ACCOUNTS = ["ravi", "anita"]

# --------------------------------------------------------------------------
# User accounts (password hashes only, generated with werkzeug pbkdf2:sha256)
# --------------------------------------------------------------------------
USERS = {
    # ---- workers ----
    "ravi": {
        "name": "Ravi Patil",
        "role": ROLE_WORKER,
        "password_hash": (
            "pbkdf2:sha256:600000$JA7h7xnvzgQJ6c0j$"
            "bdd3ec4c813672dd1f208a716a0e3a212da87918eff178676573f6a95f80036a"
        ),
    },
    "sneha": {
        "name": "Sneha Kulkarni",
        "role": ROLE_WORKER,
        "password_hash": (
            "pbkdf2:sha256:600000$IZTVioYWTrKBShud$"
            "4f2a0797bb1cfd8416796d1bdb00b1fc7c9f5dfe37796420d03a26475aa97a5c"
        ),
    },
    "amit": {
        "name": "Amit Shah",
        "role": ROLE_WORKER,
        "password_hash": (
            "pbkdf2:sha256:600000$kRdpEcBhIbWfisi2$"
            "8efaa3a25469ec10b5e3e7138d21ce6a649da7db79eb49a21c38a4c394c0c576"
        ),
    },
    "priya": {
        "name": "Priya Nair",
        "role": ROLE_WORKER,
        "password_hash": (
            "pbkdf2:sha256:600000$VF577gz3sOVTBxgK$"
            "cb1fb45cd45c68c6956d9481488a5bbaea4c4433be66d26b4fc9dd29af9660c9"
        ),
    },
    "karan": {
        "name": "Karan Mehta",
        "role": ROLE_WORKER,
        "password_hash": (
            "pbkdf2:sha256:600000$ADb0GrfwrMZHyrkB$"
            "60d2a41fe6ae67309cd797fe42daa3b2c788b013b91c3fcb25a134d439f17ad3"
        ),
    },
    # ---- managers ----
    "anita": {
        "name": "Anita Rao",
        "role": ROLE_MANAGER,
        "password_hash": (
            "pbkdf2:sha256:600000$qM8wt5ZRlmp4s5DF$"
            "d7c8c4d263ec4ef1e4e292d52427494dced089614be633dcae916fa6907cdb64"
        ),
    },
    "vikram": {
        "name": "Vikram Desai",
        "role": ROLE_MANAGER,
        "password_hash": (
            "pbkdf2:sha256:600000$VZ2LWFio9WGqHVa4$"
            "ec440e84e1c540c4ff5c3bc93a0e656ed807f29c4bfe0bf32103bd17b1493274"
        ),
    },
    "meera": {
        "name": "Meera Iyer",
        "role": ROLE_MANAGER,
        "password_hash": (
            "pbkdf2:sha256:600000$PgEoD6D23sXWRVFV$"
            "7feb995110b295da245ac2930d8c09d5753406407b0314861413eabce68b957e"
        ),
    },
}

# Used when a username does not exist, so a wrong username takes the same
# time to reject as a wrong password (prevents username enumeration by timing).
_DUMMY_HASH = generate_password_hash("not-a-real-password", method="pbkdf2:sha256:600000")


def authenticate(username, password):
    """Return the user dict (with username) if credentials are valid, else None."""
    username = (username or "").strip().lower()
    user = USERS.get(username)
    if user is None:
        check_password_hash(_DUMMY_HASH, password or "")
        return None
    if not check_password_hash(user["password_hash"], password or ""):
        return None
    return dict(user, username=username)


# --------------------------------------------------------------------------
# Persistence layer
# --------------------------------------------------------------------------
class JsonStore:
    """Thread-safe, atomic read/write wrapper around a single JSON file."""

    def __init__(self, path):
        self.path = path
        self._lock = threading.Lock()
        self._ensure_file()

    def _ensure_file(self):
        folder = os.path.dirname(os.path.abspath(self.path))
        os.makedirs(folder, exist_ok=True)
        if not os.path.exists(self.path):
            self._write({"next_id": 1, "requests": []})

    def _read(self):
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (json.JSONDecodeError, OSError):
            # Preserve the corrupt file for inspection, then start clean.
            if os.path.exists(self.path):
                backup = self.path + ".corrupt-" + datetime.now().strftime("%Y%m%d%H%M%S")
                os.replace(self.path, backup)
            data = {"next_id": 1, "requests": []}
            self._write(data)
        data.setdefault("next_id", 1)
        data.setdefault("requests", [])
        return data

    def _write(self, data):
        folder = os.path.dirname(os.path.abspath(self.path))
        fd, tmp_path = tempfile.mkstemp(dir=folder, prefix=".data-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2, ensure_ascii=False)
            os.replace(tmp_path, self.path)
        except Exception:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            raise

    def all_requests(self):
        with self._lock:
            return self._read()["requests"]

    def get(self, request_id):
        with self._lock:
            for item in self._read()["requests"]:
                if item["id"] == request_id:
                    return item
        return None

    def add(self, record):
        with self._lock:
            data = self._read()
            record["id"] = "SPR-{:04d}".format(data["next_id"])
            data["next_id"] += 1
            data["requests"].append(record)
            self._write(data)
            return record

    def update(self, request_id, mutator):
        """
        Apply mutator(record) inside the lock and persist.

        The read, the mutator's checks and the write all happen under one lock,
        so a check inside the mutator cannot be invalidated by another thread
        before the write. If the mutator returns False, nothing is written.

        Returns the updated record, False if the mutator cancelled the update,
        or None if the request does not exist.
        """
        with self._lock:
            data = self._read()
            for item in data["requests"]:
                if item["id"] == request_id:
                    if mutator(item) is False:
                        return False
                    item["updated_at"] = now_iso()
                    self._write(data)
                    return item
        return None


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def now_iso():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def clean(value):
    return (value or "").strip()


def validate_submission(form):
    """Field-level validation for a new request. Returns (cleaned, errors)."""
    errors = {}
    cleaned = {
        "part_name": clean(form.get("part_name")),
        "part_number": clean(form.get("part_number")).upper(),
        "quantity_raw": clean(form.get("quantity")),
        "urgency": clean(form.get("urgency")),
        "asset_id": clean(form.get("asset_id")).upper(),
        "requester": clean(form.get("requester")),
        "justification": clean(form.get("justification")),
    }

    if not 3 <= len(cleaned["part_name"]) <= 100:
        errors["part_name"] = "Part name must be 3 to 100 characters."

    if not PART_NUMBER_RE.match(cleaned["part_number"]):
        errors["part_number"] = (
            "Part number must be 3 to 30 characters: letters, digits, '-', '.', '/'."
        )

    try:
        quantity = int(cleaned["quantity_raw"])
        if not 1 <= quantity <= MAX_QUANTITY:
            raise ValueError
        cleaned["quantity"] = quantity
    except ValueError:
        errors["quantity"] = "Quantity must be a whole number from 1 to {}.".format(MAX_QUANTITY)

    if cleaned["urgency"] not in URGENCY_LEVELS:
        errors["urgency"] = "Select a valid urgency level."

    if not ASSET_ID_RE.match(cleaned["asset_id"]):
        errors["asset_id"] = (
            "Asset ID must be 2 to 20 characters: letters, digits, '-', '_'."
        )

    if not PERSON_NAME_RE.match(cleaned["requester"]):
        errors["requester"] = "Enter a valid name (2 to 60 letters)."

    if not 20 <= len(cleaned["justification"]) <= 1000:
        errors["justification"] = "Justification must be 20 to 1000 characters."

    return cleaned, errors


def run_validation_checks(record, all_records):
    """
    Business-rule checks executed by POST /validate/<id>.
    Returns (passed: bool, checks: list[dict]).
    Each check: {name, result: PASS|WARN|FAIL, detail}
    """
    checks = []

    def add(name, result, detail):
        checks.append({"name": name, "result": result, "detail": detail})

    # 1. Field integrity (re-run in case data.json was edited by hand)
    _, field_errors = validate_submission(
        {
            "part_name": record.get("part_name"),
            "part_number": record.get("part_number"),
            "quantity": str(record.get("quantity", "")),
            "urgency": record.get("urgency"),
            "asset_id": record.get("asset_id"),
            "requester": record.get("requester"),
            "justification": record.get("justification"),
        }
    )
    if field_errors:
        add("Field integrity", "FAIL", "; ".join(field_errors.values()))
    else:
        add("Field integrity", "PASS", "All mandatory fields are present and well-formed.")

    # 2. Duplicate: an EARLIER open request for the same part on the same asset
    def seq(rid):
        return int(rid.split("-")[1])

    duplicates = [
        r["id"]
        for r in all_records
        if seq(r["id"]) < seq(record["id"])
        and r["status"] in OPEN_STATUSES
        and r["part_number"] == record["part_number"]
        and r["asset_id"] == record["asset_id"]
    ]
    if duplicates:
        add(
            "Duplicate check",
            "FAIL",
            "An earlier open request already exists for this part on this asset: " + ", ".join(duplicates),
        )
    else:
        add("Duplicate check", "PASS", "No open duplicate for this part/asset combination.")

    # 3. Critical urgency needs a substantive justification
    if record.get("urgency") == "Critical" and len(record.get("justification", "")) < 50:
        add(
            "Critical justification",
            "FAIL",
            "Critical requests require at least 50 characters of justification.",
        )
    elif record.get("urgency") == "Critical":
        add("Critical justification", "PASS", "Justification meets critical-request threshold.")

    # 4. Bulk quantity sanity check (advisory only)
    qty = record.get("quantity", 0)
    if isinstance(qty, int) and qty > BULK_QUANTITY_THRESHOLD and record.get("urgency") == "Low":
        add(
            "Bulk quantity",
            "WARN",
            "Quantity above {} with Low urgency. Consider a planned procurement order.".format(
                BULK_QUANTITY_THRESHOLD
            ),
        )
    else:
        add("Bulk quantity", "PASS", "Quantity is within the expected range for the urgency.")

    passed = all(c["result"] != "FAIL" for c in checks)
    return passed, checks


def add_event(record, status, actor, note):
    record.setdefault("timeline", []).append(
        {"status": status, "actor": actor, "note": note, "timestamp": now_iso()}
    )


def summarize(records):
    counts = {s: 0 for s in STATUSES}
    for r in records:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    counts["Total"] = len(records)
    counts["CriticalOpen"] = sum(
        1 for r in records if r["urgency"] == "Critical" and r["status"] in OPEN_STATUSES
    )
    return counts


# --------------------------------------------------------------------------
# Application factory
# --------------------------------------------------------------------------
def create_app(data_file=None, testing=False, csrf_enabled=True, demo_mode=None):
    app = Flask(__name__, template_folder=os.path.join(BASE_DIR, "templates"))
    app.config["SECRET_KEY"] = os.environ.get("SPRS_SECRET_KEY", "sprs-dev-secret-change-me")
    app.config["TESTING"] = testing
    app.config["DATA_FILE"] = data_file or DEFAULT_DATA_FILE
    app.config["CSRF_ENABLED"] = csrf_enabled
    if demo_mode is None:
        demo_mode = os.environ.get("SPRS_DEMO_MODE", "0") == "1"
    app.config["DEMO_MODE"] = bool(demo_mode)
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(hours=8)

    store = JsonStore(app.config["DATA_FILE"])
    app.extensions["sprs_store"] = store

    # ------------------------------------------------------------------
    # Authentication, authorisation and CSRF
    # ------------------------------------------------------------------
    @app.before_request
    def load_user_and_check_csrf():
        g.user = None
        username = session.get("username")
        if username:
            user = USERS.get(username)
            if user is None:
                # Account removed from USERS while the session was alive.
                session.clear()
            else:
                g.user = dict(user, username=username)

        if "csrf_token" not in session:
            session["csrf_token"] = secrets.token_urlsafe(32)

        if request.method == "POST" and app.config["CSRF_ENABLED"]:
            sent = request.form.get("csrf_token", "")
            if not hmac.compare_digest(sent, session["csrf_token"]):
                abort(400, description="Your form session expired. Reload the page and try again.")

    @app.context_processor
    def inject_globals():
        return {
            "current_user": g.get("user"),
            "csrf_token": session.get("csrf_token", ""),
            "ROLE_WORKER": ROLE_WORKER,
            "ROLE_MANAGER": ROLE_MANAGER,
            "demo_mode": app.config["DEMO_MODE"],
            "demo_accounts": [
                dict(USERS[u], username=u) for u in DEMO_ACCOUNTS if u in USERS
            ] if app.config["DEMO_MODE"] else [],
        }

    def login_required(role=None):
        def decorator(view):
            @wraps(view)
            def wrapped(*args, **kwargs):
                if g.user is None:
                    flash("Please sign in to continue.", "warning")
                    return redirect(url_for("login", next=request.full_path.rstrip("?")))
                if role is not None and g.user["role"] != role:
                    abort(403, description="This page is only available to {}s.".format(role))
                return view(*args, **kwargs)
            return wrapped
        return decorator

    def safe_next(target):
        """Allow only local, relative redirect targets after login."""
        if target and target.startswith("/") and not target.startswith("//") and "\\" not in target:
            return target
        return url_for("dashboard")

    def visible_records():
        records = store.all_requests()
        if g.user["role"] == ROLE_MANAGER:
            return records
        return [r for r in records if r.get("requester_username") == g.user["username"]]

    def can_view(record):
        if g.user["role"] == ROLE_MANAGER:
            return True
        return record.get("requester_username") == g.user["username"]

    def render(view, **ctx):
        return render_template(
            "index.html",
            view=view,
            urgency_levels=URGENCY_LEVELS,
            statuses=STATUSES,
            **ctx
        )

    def get_or_404(request_id):
        record = store.get(request_id)
        if record is None:
            abort(404, description="Request {} was not found.".format(request_id))
        return record

    # ---------------- internal actions shared by routes ----------------
    def do_validate(request_id):
        record = get_or_404(request_id)
        actor = g.user["name"]
        if record["status"] != "Pending":
            return False, "Only Pending requests can be validated (current: {}).".format(
                record["status"]
            )

        passed, checks = run_validation_checks(record, store.all_requests())

        def mutate(r):
            # Re-check under the store lock: another manager may have acted
            # between the read above and this write.
            if r["status"] != "Pending":
                return False
            r["validation"] = {"passed": passed, "checks": checks, "checked_at": now_iso(), "checked_by": actor}
            if passed:
                r["status"] = "Validated"
                add_event(r, "Validated", actor, "All validation checks passed.")
            else:
                failed = [c["name"] for c in checks if c["result"] == "FAIL"]
                add_event(r, "Pending", actor, "Validation failed: " + ", ".join(failed))
            return True

        if store.update(request_id, mutate) is False:
            return False, "{} was changed by another manager. Reload to see its current status.".format(request_id)
        if passed:
            return True, "{} passed validation.".format(request_id)
        return False, "{} failed validation. See check results.".format(request_id)

    def do_decision(request_id, decision, notes):
        record = get_or_404(request_id)
        reviewer = g.user["name"]
        notes = clean(notes)

        if record.get("requester_username") == g.user["username"]:
            return False, "You cannot decide on a request you raised yourself."

        if decision == "Approved":
            if record["status"] != "Validated":
                return False, "Only Validated requests can be approved (current: {}).".format(
                    record["status"]
                )
        elif decision == "Rejected":
            if record["status"] not in OPEN_STATUSES:
                return False, "Only open requests can be rejected (current: {}).".format(
                    record["status"]
                )
            if len(notes) < 10:
                return False, "Rejection requires reviewer notes of at least 10 characters."
        else:
            return False, "Unknown decision."

        allowed_from = {"Validated"} if decision == "Approved" else OPEN_STATUSES
        username = g.user["username"]

        def mutate(r):
            # Re-check under the store lock, so two managers deciding at the
            # same moment cannot both succeed. Only the first write wins.
            if r["status"] not in allowed_from:
                return False
            r["status"] = decision
            r["reviewer"] = reviewer
            r["reviewer_username"] = username
            r["reviewer_notes"] = notes
            r["decided_at"] = now_iso()
            add_event(r, decision, reviewer, notes or "No notes provided.")
            return True

        if store.update(request_id, mutate) is False:
            return False, "{} was already decided by another manager. Reload to see the outcome.".format(request_id)
        return True, "{} has been {}.".format(request_id, decision.lower())

    # ---------------------------- auth routes ----------------------------
    @app.route("/login", methods=["GET", "POST"])
    def login():
        if g.user is not None:
            return redirect(url_for("dashboard"))

        next_url = request.values.get("next", "")
        if request.method == "GET":
            return render("login", username="", next_url=next_url)

        username = clean(request.form.get("username"))
        user = authenticate(username, request.form.get("password", ""))
        if user is None:
            flash("Invalid username or password.", "danger")
            return render("login", username=username, next_url=next_url), 401

        start_session(user)
        return redirect(safe_next(next_url))

    def start_session(user, demo=False):
        # New session on login (prevents session fixation), with a fresh CSRF token.
        session.clear()
        session.permanent = True
        session["username"] = user["username"]
        session["csrf_token"] = secrets.token_urlsafe(32)
        flash(
            "Signed in as {} ({}){}.".format(
                user["name"], user["role"], " via demo quick sign-in" if demo else ""
            ),
            "success",
        )

    @app.route("/login/demo", methods=["POST"])
    def demo_login():
        # 404 when demo mode is off, so the route does not even appear to exist.
        if not app.config["DEMO_MODE"]:
            abort(404, description="Page not found.")
        username = clean(request.form.get("username")).lower()
        if username not in DEMO_ACCOUNTS or username not in USERS:
            abort(400, description="That account is not available for demo sign-in.")
        start_session(dict(USERS[username], username=username), demo=True)
        return redirect(safe_next(request.form.get("next", "")))

    @app.route("/logout", methods=["POST"])
    def logout():
        session.clear()
        flash("You have been signed out.", "success")
        return redirect(url_for("login"))

    # ---------------------------- app routes ----------------------------
    @app.route("/", methods=["GET"])
    @login_required()
    def dashboard():
        records = visible_records()
        status_filter = request.args.get("status", "")
        urgency_filter = request.args.get("urgency", "")
        query = clean(request.args.get("q")).lower()

        filtered = records
        if status_filter in STATUSES:
            filtered = [r for r in filtered if r["status"] == status_filter]
        elif status_filter == "Open":
            filtered = [r for r in filtered if r["status"] in OPEN_STATUSES]
        if urgency_filter in URGENCY_LEVELS:
            filtered = [r for r in filtered if r["urgency"] == urgency_filter]
        if query:
            filtered = [
                r
                for r in filtered
                if query in r["id"].lower()
                or query in r["part_name"].lower()
                or query in r["part_number"].lower()
                or query in r["asset_id"].lower()
                or query in r["requester"].lower()
            ]

        urgency_rank = {u: i for i, u in enumerate(reversed(URGENCY_LEVELS))}
        filtered = sorted(
            filtered,
            key=lambda r: (r["status"] not in OPEN_STATUSES, urgency_rank[r["urgency"]], r["id"]),
        )

        return render(
            "dashboard",
            requests=filtered,
            summary=summarize(records),
            filters={"status": status_filter, "urgency": urgency_filter, "q": query},
            form={},
            errors={},
        )

    @app.route("/submit", methods=["GET", "POST"])
    @login_required(role=ROLE_WORKER)
    def submit():
        if request.method == "GET":
            return render("submit", form={}, errors={})

        # The requester is always the signed-in worker, never a form field.
        data = request.form.to_dict()
        data["requester"] = g.user["name"]
        cleaned, errors = validate_submission(data)
        if errors:
            flash("The request could not be submitted. Correct the highlighted fields.", "danger")
            return render("submit", form=cleaned, errors=errors), 400

        timestamp = now_iso()
        record = {
            "part_name": cleaned["part_name"],
            "part_number": cleaned["part_number"],
            "quantity": cleaned["quantity"],
            "urgency": cleaned["urgency"],
            "asset_id": cleaned["asset_id"],
            "requester": g.user["name"],
            "requester_username": g.user["username"],
            "justification": cleaned["justification"],
            "status": "Pending",
            "created_at": timestamp,
            "updated_at": timestamp,
            "reviewer": None,
            "reviewer_username": None,
            "reviewer_notes": None,
            "decided_at": None,
            "validation": None,
            "timeline": [
                {
                    "status": "Pending",
                    "actor": g.user["name"],
                    "note": "Request submitted.",
                    "timestamp": timestamp,
                }
            ],
        }
        saved = store.add(record)
        flash("Request {} submitted successfully.".format(saved["id"]), "success")
        return redirect(url_for("status", request_id=saved["id"]))

    @app.route("/validate/<request_id>", methods=["POST"])
    @login_required(role=ROLE_MANAGER)
    def validate(request_id):
        ok, message = do_validate(request_id)
        flash(message, "success" if ok else "warning")
        return redirect(url_for("review", request_id=request_id))

    @app.route("/review/<request_id>", methods=["GET", "POST"])
    @login_required(role=ROLE_MANAGER)
    def review(request_id):
        record = get_or_404(request_id)
        if request.method == "POST":
            action = request.form.get("action")
            notes = request.form.get("notes", "")
            if action == "validate":
                ok, message = do_validate(request_id)
            elif action == "approve":
                ok, message = do_decision(request_id, "Approved", notes)
            elif action == "reject":
                ok, message = do_decision(request_id, "Rejected", notes)
            else:
                ok, message = False, "Unknown review action."
            flash(message, "success" if ok else "danger")
            if ok and action in ("approve", "reject"):
                return redirect(url_for("status", request_id=request_id))
            return redirect(url_for("review", request_id=request_id))
        return render("review", req=record)

    @app.route("/approve/<request_id>", methods=["POST"])
    @login_required(role=ROLE_MANAGER)
    def approve(request_id):
        ok, message = do_decision(request_id, "Approved", request.form.get("notes", ""))
        flash(message, "success" if ok else "danger")
        target = "status" if ok else "review"
        return redirect(url_for(target, request_id=request_id))

    @app.route("/reject/<request_id>", methods=["POST"])
    @login_required(role=ROLE_MANAGER)
    def reject(request_id):
        ok, message = do_decision(request_id, "Rejected", request.form.get("notes", ""))
        flash(message, "success" if ok else "danger")
        target = "status" if ok else "review"
        return redirect(url_for(target, request_id=request_id))

    @app.route("/status/<request_id>", methods=["GET"])
    @login_required()
    def status(request_id):
        record = get_or_404(request_id)
        if not can_view(record):
            # Same response as a missing ID, so workers cannot probe other people's requests.
            abort(404, description="Request {} was not found.".format(request_id))
        return render("status", req=record)

    @app.route("/health", methods=["GET"])
    def health():
        return {"status": "ok", "requests": len(store.all_requests())}, 200

    @app.errorhandler(400)
    def bad_request(err):
        return render("error", error_code=400, error_message=err.description), 400

    @app.errorhandler(403)
    def forbidden(err):
        return render("error", error_code=403, error_message=err.description), 403

    @app.errorhandler(404)
    def not_found(err):
        return render("error", error_code=404, error_message=err.description), 404

    @app.errorhandler(405)
    def method_not_allowed(err):
        return render("error", error_code=405, error_message="Method not allowed for this URL."), 405

    @app.errorhandler(500)
    def server_error(err):
        return render("error", error_code=500, error_message="Internal server error."), 500

    return app


def hash_password_cli():
    """Prompt for a password and print the hash to paste into USERS."""
    first = getpass.getpass("New password: ")
    second = getpass.getpass("Repeat password: ")
    if first != second:
        print("Passwords do not match.")
        sys.exit(1)
    if len(first) < 8:
        print("Use at least 8 characters.")
        sys.exit(1)
    print(generate_password_hash(first, method="pbkdf2:sha256:600000"))


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "hash-password":
        hash_password_cli()
        sys.exit(0)

    demo = "--demo" in sys.argv[1:]
    app = create_app(demo_mode=True if demo else None)
    if app.config["DEMO_MODE"]:
        print(" * DEMO MODE ON: one-click sign-in is enabled. Never use this outside a demo.")
    app.run(
        host=os.environ.get("SPRS_HOST", "127.0.0.1"),
        port=int(os.environ.get("SPRS_PORT", "5000")),
        debug=os.environ.get("SPRS_DEBUG", "0") == "1",
    )
else:
    app = create_app()
    