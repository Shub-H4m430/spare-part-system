# Final Report: Spare Parts Request System (SPRS)

## 1. Summary of the Delivered System

SPRS is a Flask web application that replaces paper spare part requisition slips in a maintenance department. It was delivered with:

- Role-based sign-in for five worker accounts and three manager accounts, with hashed passwords
- Request submission with field-level validation, and the requester taken from the session
- Four automated validation checks: field integrity, duplicate detection, Critical justification and bulk quantity
- Manager approval and rejection, with mandatory notes on rejection and a guard against self-approval
- A lifecycle timeline and progress bar on every request
- Separate worker and manager dashboards, with search, filters and summary counters
- JSON file persistence with atomic writes and automatic corrupt-file recovery
- CSRF protection on every form, a `/health` endpoint, and an optional demo mode for presentations

Around the application, a complete DevOps workflow was delivered:

- A declarative **Jenkins pipeline** with a quality gate of Flake8 linting and six Selenium browser tests run by pytest against a temporary test port
- A **multi-stage Docker image** that runs as the non-root system user `sprs`, deployed with Docker Compose on a persistent named volume
- Versioned images **published to Docker Hub** under the namespace `5be4eb7d3ebdb885f`, with the tags `v1` and `build-7`
- An idempotent **Ansible playbook** that provisions the workspace, checks prerequisites, enforces file permissions and manages `.gitignore`

The full design is documented in `architecture.md`, the backlog and process in `agile_plan.md`, and the motivation in `problem_statement.md`.

## 2. Running the Application

### 2.1 Locally with Python

```bash
python -m venv venv
# Windows:        venv\Scripts\activate
# macOS / Linux:  source venv/bin/activate
pip install -r requirements.txt
python src/app.py            # normal mode
python src/app.py --demo     # with one-click demo sign-in
```

Open `http://127.0.0.1:5000` in a browser. To show a worker and a manager side by side in the same browser, open one at `http://localhost:5000` and the other at `http://127.0.0.1:5000`. The browser stores a separate session cookie for each address, so both stay signed in.

### 2.2 With Docker Compose

Run from the project root:

```bash
# One time: create a random session secret. docker/.env is excluded from Git.
python -c "import secrets; print('SPRS_SECRET_KEY=' + secrets.token_hex(32))" > docker/.env

docker compose -f docker/docker-compose.yml up -d --build   # build and start
docker compose -f docker/docker-compose.yml ps               # wait for "healthy"
docker compose -f docker/docker-compose.yml logs -f          # follow logs
docker compose -f docker/docker-compose.yml down             # stop, data is kept
```

Data lives in the named volume `spare-parts-data` and survives restarts and rebuilds. `docker compose ... down -v` deletes it.

### 2.3 From the published Docker Hub image

```bash
docker pull 5be4eb7d3ebdb885f/spare-parts-app:build-7
docker run -d --name spare-parts-app -p 5000:5000 \
  -e SPRS_SECRET_KEY=<a long random value> \
  -v spare-parts-data:/data \
  5be4eb7d3ebdb885f/spare-parts-app:build-7
```

### 2.4 Preparing a workspace with Ansible

```bash
pip install ansible-core
ansible-playbook -i ansible/hosts ansible/site.yml
```

Run it once after cloning, and again whenever the workspace may have drifted. A healthy workspace reports `changed=0`.

### 2.5 Running the UI tests

```bash
pytest tests/selenium/test_spare_parts_ui.py -v
```

Without `SPRS_BASE_URL`, the suite starts its own server on a free port with a temporary data file. To test a server that is already running, set `SPRS_BASE_URL`, for example `SPRS_BASE_URL=http://127.0.0.1:5055`.

## 3. Troubleshooting Guide

### 3.1 Port 5000 is already in use

**Symptom.** The server fails to start with `Address already in use`, or on Windows `An attempt was made to access a socket in a way forbidden by its access permissions`.

**Cause.** Another program is using the port. On macOS 12 and later, the AirPlay Receiver service listens on port 5000 by default. On any system, an older copy of SPRS may still be running in another terminal.

**Fix.** Start SPRS on a different port:

```bash
# macOS / Linux
SPRS_PORT=5050 python src/app.py

# Windows Command Prompt
set SPRS_PORT=5050
python src\app.py

# Windows PowerShell
$env:SPRS_PORT="5050"
python src\app.py
```

To find what holds the port, run `lsof -i :5000` on macOS or Linux, or `netstat -ano | findstr :5000` on Windows and look up the process ID in Task Manager. On macOS you can also turn off AirPlay Receiver in System Settings under General, AirDrop and Handoff.

### 3.2 `ModuleNotFoundError: No module named 'flask'`

**Cause.** The dependencies were installed into a different Python environment than the one running the app, or were never installed.

**Fix.**

1. Activate the virtual environment (see section 2). The prompt should show `(venv)`.
2. Run `pip install -r requirements.txt`.
3. Confirm with `python -c "import flask; print('flask ok')"`.

On Windows, if `python` opens the Microsoft Store, use `py` instead, for example `py -m venv venv`. If `pip` installs into the wrong Python, use `python -m pip install -r requirements.txt`, which always targets the interpreter you are running.

### 3.3 An unexpected `ImportError` coming from inside Flask

**Symptom.** A traceback that ends inside Flask's own files, for example while it imports `click`, `json` or `flask`.

**Cause.** A file in the project folder has the same name as a library, such as `click.py`, `json.py` or `flask.py`. Python imports the local file instead of the real library.

**Fix.** Rename the local file and delete any `__pycache__` folders next to it.

### 3.4 The page loads but has no styling

**Cause.** Bootstrap, Bootstrap Icons and the IBM Plex fonts are loaded from public CDNs. Without internet access the page renders as plain HTML. The application itself still works.

**Fix.** Connect to the internet, or for an offline lab download `bootstrap.min.css`, `bootstrap.bundle.min.js` and the Bootstrap Icons font folder into a `src/static/` folder and point the `<link>` and `<script>` tags in `index.html` to them with `url_for('static', filename=...)`.

### 3.5 "Your form session expired. Reload the page and try again."

**Cause.** The form's CSRF token did not match the one stored in the session. This happens when a page was left open across a server restart with a new `SPRS_SECRET_KEY`, when the 8-hour session expired, or when a form was submitted from a page cached before the user signed in again.

**Fix.** Reload the page and submit again. If it happens on every submission, check that the browser is accepting cookies for the site.

### 3.6 Signing in on one tab signs out another tab

**Cause.** Tabs on the same address share one session cookie, so the most recent sign-in replaces the earlier one. This is normal browser behaviour.

**Fix.** Use `localhost` for one role and `127.0.0.1` for the other, or use a private window for the second role.

### 3.7 Demo buttons do not appear on the sign-in page

**Cause.** Demo mode is off by default.

**Fix.** Start with `python src/app.py --demo`, or set `SPRS_DEMO_MODE=1`. The terminal prints `DEMO MODE ON` and a DEMO MODE badge appears in the navbar.

### 3.8 A worker cannot see requests that exist in `data.json`

**Cause.** The requests were created by an older version of the application that did not record `requester_username`. Workers only see requests whose `requester_username` matches their own.

**Fix.** Managers still see these requests. For a clean start, stop the server and delete `data.json`. It is recreated empty on the next start.

### 3.9 Corrupt `data.json` recovery

**Symptom.** All requests seem to have disappeared, and a file named like `data.json.corrupt-20261102141530` has appeared next to `data.json`.

**Cause.** The file contained invalid JSON, usually after a hand edit with a missing comma or quote. SPRS never deletes data. It moves the unreadable file aside with a timestamp and starts a fresh, empty store so the application keeps working.

**Recovery steps.**

1. Stop the server with Ctrl+C so nothing writes to the store during recovery.
2. Find the exact error in the preserved file:
   ```bash
   python -m json.tool src/data.json.corrupt-20261102141530
   ```
   The message reports the line and column of the problem, for example `Expecting ',' delimiter: line 42 column 7`.
3. Open the file in a text editor, go to that line, and fix it. Run the command from step 2 again until it prints the formatted JSON without an error.
4. Check that `next_id` is greater than the highest request number in the file. If the last request is `SPR-0012`, `next_id` must be at least `13`, otherwise new requests would reuse an existing ID.
5. Replace the empty store with the repaired file:
   ```bash
   # macOS / Linux
   mv src/data.json.corrupt-20261102141530 src/data.json
   # Windows
   move src\data.json.corrupt-20261102141530 src\data.json
   ```
   If requests were submitted between the corruption and the recovery, copy them from the new `data.json` into the repaired file first, giving them new IDs from `next_id` upwards.
6. Start the server and confirm the requests are back. `GET /health` reports the request count.

**Prevention.** Avoid editing `data.json` by hand while the server is running. The server rewrites the whole file on every change and will overwrite manual edits made at the same time.

### 3.10 Selenium tests cannot start a browser

**Cause.** Selenium needs Google Chrome installed and a matching ChromeDriver. `webdriver-manager` downloads the driver on first use, which needs internet access.

**Fix.** Install Chrome, and run the tests once with internet access so the driver is cached. Selenium 4.6 and later also includes Selenium Manager, which can locate a driver without `webdriver-manager`. If Chrome and the driver versions differ, set `CHROMEDRIVER_PATH` to a driver that matches your Chrome version, and `CHROME_BIN` to the Chrome binary if it is not on the default path.

### 3.11 Docker Compose says `SPRS_SECRET_KEY is not set`

**Cause.** Compose requires a session secret and refuses every command without one, including `down`. This is deliberate, so the public development key can never reach a container.

**Fix.** Create `docker/.env` with the one-line command in section 2.2, then run the command again.

### 3.12 Jenkins quality gate fails with "SPRS did not become healthy"

**Cause.** The test server could not start on port 5055, usually because another process holds that port, or because the app crashed at start-up.

**Fix.** Open the archived `ci-data/app.log` in the build's artifacts. If the port is taken, find the process with `lsof -i :5055` and stop it, or change `TEST_PORT` and `TEST_BASE_URL` in the `environment` block of the Jenkinsfile.

### 3.13 A Selenium test fails in Jenkins but passes locally

**Fix.** Open the build's archived artifacts. `tests/selenium/artifacts/` holds a screenshot and the page HTML for each failed test, showing exactly what the browser saw. The JUnit report on the build page lists the failed assertion.

### 3.14 The Deploy stage fails with "Container did not become healthy"

**Cause.** The container started but `/health` never answered `ok`, often because the `sprs-secret-key` credential is missing in Jenkins or the image failed at start-up.

**Fix.** Read the last 100 log lines that the stage prints. Check that a Secret text credential with ID `sprs-secret-key` exists under Manage Jenkins, then Credentials.

### 3.15 `docker push` is denied

**Cause.** The local image is not tagged with the Docker Hub namespace, or the session is not logged in to that account.

**Fix.** Run `docker login -u 5be4eb7d3ebdb885f`, re-tag the image as `5be4eb7d3ebdb885f/spare-parts-app:<tag>`, and push again. The namespace in the tag must exactly match the logged-in account.

### 3.16 Container cannot write to a bind-mounted data folder

**Cause.** The app runs as user ID 10001, not root. A host folder bind-mounted at `/data` is usually owned by your own user, so the container cannot write to it.

**Fix.** Use the named volume from `docker-compose.yml`, which Docker creates with the right owner. If a host folder is required, give it to the container's user with `sudo chown 10001:10001 <folder>`.

### 3.17 Ansible fails or is not available

- **`Missing required files: ...`** The playbook is run from the wrong folder, or a project file was deleted. Run it from the project root and restore the listed files.
- **`Python 3.10 or newer is required`** Install a newer Python and make sure `python3` points to it.
- **Ansible on Windows.** Ansible does not run natively on Windows. Use Windows Subsystem for Linux (WSL) and run the playbook from inside it.

## 4. Current System Limitations

### 4.1 Storage and concurrency

- **The lock protects only one process.** `JsonStore` serialises reads and writes with a `threading.Lock`. This is correct for the Flask development server and for the container, where Gunicorn runs one worker process with eight threads. If Gunicorn were configured with several workers, each process would have its own lock. Two simultaneous decisions could then each read the file, change it, and write it back, and the second write would silently discard the first.
- **Duplicate detection can be raced.** Decisions are safe because their status check runs inside the same lock as the write. The duplicate check, however, scans all requests before the locked write. If two managers validate two duplicate requests at exactly the same moment, both could pass. This is unlikely in practice and disappears with a database unique constraint in Phase 2 of the roadmap.
- **Every change rewrites the whole file.** Saving one approval reads and writes every request. This is fast for hundreds or a few thousand requests, but the cost grows with the size of the file.
- **No indexing or pagination.** The dashboard loads every visible request on each page view.
- **Timestamps are local server time without a time zone.** Moving the server to another time zone, or a daylight saving change, would make timelines ambiguous.

### 4.2 Security and identity

- **User accounts are defined in code.** Adding a user, removing one, or changing a password means editing `app.py` and restarting. There is no administration screen.
- **No enterprise authentication.** There is no LDAP, Active Directory or single sign-on integration, so employees need separate SPRS credentials.
- **No password reset, account lockout or rate limiting.** Repeated wrong passwords are not slowed down or blocked.
- **The default secret key is public.** `SPRS_SECRET_KEY` falls back to a value that is visible in the source code. Anyone who knows it can forge session cookies, so a real key must be set for any shared deployment.
- **No HTTPS.** The built-in server speaks plain HTTP. Passwords and session cookies would cross the network unencrypted if the app were opened from another machine.
- **Demo mode is a deliberate bypass.** It is off by default and clearly labelled, but starting a shared server with `--demo` would let anyone sign in as a manager.

### 4.3 Functional scope

- The **Released to Stores** step on the progress bar is informational. No role can confirm that a part was physically issued.
- A rejected request cannot be edited and resubmitted. The technician has to raise a new request.
- There are no notifications. Users must open the application to see changes.
- There is no inventory data, so the system cannot warn that a part is out of stock.
- Local runs use Flask's development server, which is not designed for production traffic. The container uses Gunicorn, but still without HTTPS.

### 4.4 DevOps and delivery

- **Publishing to Docker Hub is manual.** A person must log in and push after a green build, so a release can be forgotten or pushed from the wrong build.
- **The image includes test tools.** The same `requirements.txt` is installed for testing and for the runtime image, so Selenium, pytest and Flake8 are inside the production image. A separate runtime requirements file would make it smaller and reduce its attack surface.
- **No image vulnerability scanning.** Neither the base image nor the installed packages are scanned for known vulnerabilities before release.
- **Deployment is single-host.** The Deploy stage recreates one container on the Jenkins host. There is no automatic rollback if a release misbehaves after it becomes healthy, although any earlier `build-N` image can be redeployed by hand.
- **The `v1` tag is mutable.** It is overwritten by each release, so only the `build-N` tags identify an exact version.
- **Ansible manages only the local workspace.** It does not yet provision the Jenkins agent or a deployment server.
- **Test coverage is end-to-end only.** The six Selenium tests cover the worker's main flow and one access rule. Manager approval, validation rules and concurrency are not yet covered by automated tests in the pipeline.

## 5. Future Enhancements Roadmap

The roadmap is ordered so that each phase removes a limitation that blocks the next one.

### Phase 1: Production hardening

- Put the Gunicorn container behind a reverse proxy, such as Nginx, that terminates HTTPS.
- Require `SPRS_SECRET_KEY` to be set, and refuse to start without it outside demo mode.
- Add login rate limiting and temporary account lockout after repeated failures.
- Bundle Bootstrap and fonts locally so the UI works offline.
- Store timestamps in UTC with time zone information and convert them for display.

### Phase 2: Migration from JSON to PostgreSQL

- Introduce SQLAlchemy models for `Request`, `ValidationRun`, `TimelineEvent` and `User`, with Alembic for schema migrations.
- Replace `JsonStore` with a repository class that has the same methods (`all_requests`, `get`, `add`, `update`). Because every route already goes through this interface, the routes and templates do not need to change.
- Use row-level locking (`SELECT ... FOR UPDATE`) in decisions, so concurrent approvals are safe across many processes.
- Write a one-time import script that loads the existing `data.json` into the database.
- Move user accounts from code into a `users` table, and add an administrator screen.

### Phase 3: Workflow and notifications

- Add a **store clerk** role that confirms issue of approved parts, completing the Released to Stores step with its own timeline event.
- Send email notifications on decisions, and immediate alerts to managers for Critical requests. Delivery should run in a background job queue such as Celery or RQ with Redis, so a slow mail server never delays a page.
- Allow a technician to edit and resubmit a rejected request, keeping the original as linked history.
- Link part numbers to an inventory table to show stock levels on the review page.

### Phase 4: DevOps automation and container scaling

Already delivered in this release: the Jenkins pipeline with a lint and Selenium quality gate, the hardened multi-stage Docker image, Compose deployment with a health check, versioned images on Docker Hub, and the idempotent Ansible workspace playbook. The remaining work is:

- Add a **Push** stage to the Jenkinsfile that publishes `v1` and `build-N` to Docker Hub using a Jenkins credential, so every green build is released automatically.
- Add **pytest unit and API tests** for the manager workflow, the validation rules and the concurrency guard, and run them in the quality gate before the browser tests.
- Scan images with a tool such as **Trivy** and fail the pipeline on critical vulnerabilities.
- Split dependencies into runtime and development files so the production image contains no test tools.
- Extend the Ansible playbook with roles that provision the Jenkins agent and a deployment server over SSH.
- Deploy to Kubernetes with several replicas behind a Service, using `/health` for the readiness and liveness probes, and configuration and secrets injected through ConfigMaps and Secrets. Horizontal scaling only becomes safe after Phase 2, because several replicas sharing one JSON file would overwrite each other's changes.

### Phase 5: Enterprise integration and insight

- Replace local accounts with LDAP or Active Directory, or with single sign-on through SAML or OpenID Connect.
- Add an analytics view: approval lead time, rejection reasons, and parts consumption per machine to support preventive maintenance planning.
- Expose a REST API so the plant's ERP or CMMS can create and read requests.

## 6. DevOps Implementation Evidence

### 6.1 Jenkins pipeline

| Stage | Evidence of success |
|---|---|
| Checkout | Commit hash, author and message printed in the console |
| Build / Setup | Fresh virtual environment, all requirements installed, `pip check` clean |
| Quality Gate | Flake8 reports zero warnings. SPRS reports healthy on port 5055. pytest reports **6 passed** for the Selenium suite, with results published as JUnit XML |
| Docker Build | Image tagged `spare-parts-app:v1` and `spare-parts-app:build-7` |
| Deploy | Container `spare-parts-app` reported `healthy` by Docker and serving on port 5000 |

The gate was also checked in the failing direction: when a test assertion fails, pytest exits with an error, the pipeline stops at the Quality Gate stage, and no Docker image is built.

### 6.2 Container and registry

- The container runs as `uid=10001(sprs)`. Attempts to write to `/app/src` or `/etc` inside it fail with `Read-only file system`.
- Data written through the app was still present after `docker compose down` followed by `up`, and after a redeployment by the pipeline, confirming the named volume.
- The image is published as `5be4eb7d3ebdb885f/spare-parts-app:v1` and `5be4eb7d3ebdb885f/spare-parts-app:build-7`.

### 6.3 Ansible idempotency

| Run | `PLAY RECAP` |
|---|---|
| First run on the workspace | `changed=1` to `changed=2`, `failed=0`, depending on the starting state |
| Second run, immediately after | `changed=0`, `failed=0` |

The first run brought the workspace to the declared state, for example by adding `.gitignore` entries or correcting a permission. The second run found nothing to change, which shows that the playbook is safe to re-run at any time and only ever removes configuration drift. As a negative check, temporarily renaming `src/app.py` makes the playbook stop with `Missing required files: src/app.py`.

## 7. Viva Presentation Script

**Target length:** about 2 minutes at a calm speaking pace. Suggested on-screen material is shown in italics.

---

**[0:00 – 0:15] The problem**

*Show the login page.*

Good morning. My project is the Spare Parts Request System. When a machine breaks down, technicians still use paper slips to request parts. Slips wait for signatures, get lost, and nobody can see their status. My system replaces that slip with a web app that needs no database server.

**[0:15 – 0:40] How it works**

*Sign in as the worker on localhost and raise a request, then sign in as the manager on 127.0.0.1.*

There are two roles. A worker raises a request, and every field is validated. A manager then runs four automated checks. They catch bad data, duplicate requests, weak Critical justifications and oversized low-urgency orders. Only a validated request can be approved, and a rejection always needs a reason. Every step is recorded in a timeline the worker can follow.

**[0:40 – 1:00] Architecture**

*Show the component diagram in architecture.md.*

It is built with Flask. Every request passes a hook that loads the user and checks a CSRF token. A decorator then checks the role. All storage goes through one class, JsonStore. It writes a temporary file and swaps it in under a lock, so a crash never leaves half a file.

**[1:00 – 1:25] Security guards**

*As the worker, open a review URL directly to show the 403 page.*

Security never depends on hiding buttons. Every route is checked on the server, so a worker calling the approve URL gets a 403. Names come from the session, not the form, so nobody can act as someone else. A manager cannot approve their own request. And if two managers decide at once, only the first decision is saved.

**[1:25 – 2:00] DevOps and close**

*Show the Jenkins stage view, then the Ansible second-run recap.*

Every change goes through a Jenkins pipeline. Flake8 linting is the first gate. Then the app starts on a separate test port, and six Selenium tests drive a real browser. If anything fails, no image is built. The image is multi-stage and runs as a non-root user, and released versions are on Docker Hub. Ansible prepares the workspace and locks down permissions, and its second run reports zero changes. Next, I would move to PostgreSQL. Thank you.

---

### Likely examiner questions and short answers

**Why JSON and not SQLite?**
The brief ruled out a database. JSON with atomic replace met the requirement with zero dependencies, and every route talks to the store through one class, so moving to a real database later is a contained change.

**What happens if two managers approve at the same moment?**
Only the first decision is saved. The status is checked again inside the same lock as the write, so the second manager is told the request was already decided. My first version checked the status before taking the lock, and a concurrency test showed both decisions being saved. Moving the check inside the lock fixed it. This holds within one server process. With several processes the lock would not be shared, which is why a database is the first item on the roadmap.

**Why does a worker get 404 instead of 403 for someone else's request?**
A 403 tells the worker the request exists. A 404 reveals nothing, so request IDs cannot be used to probe other people's work.

**Is demo mode a security hole?**
Only when switched on. It is off by default, it is a separate route that returns 404 when disabled, it is limited to two named accounts, and a DEMO MODE badge appears on every page while it is active.

**Why does the duplicate check only look at earlier requests?**
If it compared against all open requests, the original request would also fail because of its own later duplicate, and neither could ever be approved.

**Why do the CI tests use port 5055 instead of 5000?**
After the first deployment, the live container holds port 5000. Tests on the same port would fail on every later build, so the quality gate uses its own port while the current release keeps running.

**Why does Gunicorn run only one worker?**
The JSON store is protected by a thread lock, which works across threads but not across processes. Several workers would each have their own lock and could overwrite each other's changes. One worker with eight threads keeps the guarantee.

**Why run the container as a non-root user?**
If an attacker found a flaw in the app, they would be an unprivileged user in a container with a read-only filesystem and no Linux capabilities, rather than root.

**What does idempotent mean, and how did you prove it?**
Running the playbook once or many times leaves the workspace in the same state. The first run made one or two changes to reach the declared state. The second run reported `changed=0`, so the playbook only corrects drift and never causes it.

**Why push two tags to Docker Hub?**
`v1` is a stable name for the current release. `build-7` never changes, so a running container can always be traced to the exact Jenkins build and commit, and an older build can be redeployed for rollback.

**Why was the Docker Hub push done manually?**
Publishing to a public registry is a deliberate release decision, and keeping it manual meant no registry password had to be stored in Jenkins. Automating it with a Jenkins credential is the first item in Phase 4 of the roadmap.
