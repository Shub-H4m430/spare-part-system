# ⚙️ Spare Parts Request System (SPRS)

[![Python Version](https://img.shields.io/badge/python-3.10%20%7C%203.12-blue.svg)](https://www.python.org/)
[![Framework](https://img.shields.io/badge/framework-Flask%203.x-green.svg)](https://flask.palletsprojects.org/)
[![Containerization](https://img.shields.io/badge/docker-multi--stage-blue)](https://www.docker.com/)
[![CI/CD](https://img.shields.io/badge/jenkins-pipeline-red)](https://www.jenkins.io/)
[![Config Management](https://img.shields.io/badge/ansible-idempotent-black)](https://www.ansible.com/)
[![License](https://img.shields.io/badge/license-Academic--Use-lightgrey.svg)]()

> **An Enterprise-Grade, End-to-End Automated DevOps Implementation**  
> Replacing manual, error-prone paper requisition slips in industrial plant operations with a lightweight, secure Python/Flask web application backed by an automated CI/CD pipeline, container registry deployment, and idempotent configuration management.

---

## 📋 Table of Contents
1. [Executive Summary & Problem Statement](#-executive-summary--problem-statement)
2. [Core Application Architecture](#-core-application-architecture)
3. [User Roles & Functional Capabilities](#-user-roles--functional-capabilities)
4. [Complete 15-Stage DevOps Lifecycle](#-complete-15-stage-devops-lifecycle)
5. [Configuration Management & Idempotency (Ansible)](#-configuration-management--idempotency-ansible)
6. [CI/CD Pipeline & Quality Gates (Jenkins)](#-cicd-pipeline--quality-gates-jenkins)
7. [Containerization & Deployment (Docker)](#-containerization--deployment-docker)
8. [Local Installation & Setup Guide](#-local-installation--setup-guide)
9. [Automated Testing Suite](#-automated-testing-suite)
10. [Repository Structure](#-repository-structure)
11. [Troubleshooting Guide](#-troubleshooting-guide)
12. [Future Enhancements & Roadmap](#-future-enhancements--roadmap)

---

## 🎯 Executive Summary & Problem Statement

In heavy manufacturing environments, unplanned equipment breakdowns incur substantial financial costs per minute of downtime. Technicians on the shop floor historically rely on paper requisition slips to request spare replacement parts from physical stores.

### Manual Process Vulnerabilities:
* **Severe Approval Delays:** Paper slips require physical manager signatures, stalling critical repairs across shift changes.
* **Lost Slips & Duplication:** Misplaced slips prompt technicians to resubmit duplicate requests, leading to double-issuing of costly inventory.
* **Zero Audit Trails:** Unrecorded rejections lack clear explanations, preventing technicians from rectifying data entry errors.
* **Lack of Operational Visibility:** Plant managers lack central visibility into critical breakdown counts or part consumption rates per machine.

### The SPRS Solution:
The **Spare Parts Request System (SPRS)** digitizes the requisition workflow. Technicians raise requests digitally in under 60 seconds; an automated engine evaluates business rules; managers review, approve, or reject requests with mandatory reasoning; and every step is recorded in a real-time, audit-ready lifecycle timeline.

---

## 🏗️ Core Application Architecture

SPRS is engineered as a lightweight, zero-external-database web service running on Flask and Gunicorn WSGI servers, designed specifically for constrained operating environments.

```
+-----------------------------------------------------------------------+
|                             CLIENT LAYER                              |
|                       Bootstrap 5 Responsive UI                       |
+-----------------------------------------------------------------------+
                                   | (HTTP / Session Cookie)
                                   v
+-----------------------------------------------------------------------+
|                          FLASK SERVER ENGINE                          |
|  +-----------------------------------------------------------------+  |
|  | before_request: Session Verification & CSRF Token Validation    |  |
|  +-----------------------------------------------------------------+  |
|  | login_required(role): Server-Side RBAC Guard                       |  |
|  +-----------------------------------------------------------------+  |
|  | Business Rules & Automated Validation Engine (Field/Dup/Bulk)   |  |
|  +-----------------------------------------------------------------+  |
|  | JsonStore: Thread-Locked Mutator with Atomic OS File Replace        |  |
|  +-----------------------------------------------------------------+  |
+-----------------------------------------------------------------------+
                                   | (Atomic Replace: os.replace)
                                   v
+-----------------------------------------------------------------------+
|                           PERSISTENCE LAYER                           |
|      /src/data.json  <--->  /src/data.json.corrupt-<timestamp>        |
+-----------------------------------------------------------------------+
```

### Architectural Highlights:
* **Atomic JSON Storage:** All state is persisted to `data.json`. Writes utilize a temporary file (`.tmp`) swapped in atomically via `os.replace` under a `threading.Lock`, guaranteeing zero data loss or corruption during power failures or process terminations.
* **Corrupt File Auto-Recovery:** If `data.json` experiences invalid JSON syntax, SPRS renames the corrupted file to `data.json.corrupt-<timestamp>`, logs an emergency event, initializes a clean store, and continues serving requests without downtime.
* **High-Iteration Hashing:** Passwords are stored securely as PBKDF2-SHA256 salted hashes with **600,000 iterations** via Werkzeug security modules.

---

## 👥 User Roles & Functional Capabilities

| Role | Access Level | Primary Capabilities |
| :--- | :--- | :--- |
| **Worker** *(Technician)* | `worker` | Submit spare part requests; view own dashboard; track real-time progress bars; view decision notes. Blocked from viewing other workers' requests (returns `404 Not Found`). |
| **Manager** *(Engineer)* | `manager` | View plant-wide dashboard; filter/search by urgency (`Critical`, `High`, etc.); run automated 4-tier validation engines; approve/reject with mandatory notes. Blocked from self-approving self-raised requests. |
| **Anonymous** | `none` | Access limited exclusively to `/login` and unauthenticated `/health` status endpoints. |

---

## ⚙️ Complete 15-Stage DevOps Lifecycle

This repository contains the complete implementation across all 15 DevOps workflow stages:

1. **Stage 1 (Version Control):** Modular Git branch flow (`develop` / `main`) with strictly enforced `.gitignore` security rules.
2. **Stage 2 (Agile Tracking):** Complete Kanban product backlog, MoSCoW prioritization, and user stories.
3. **Stage 3 (System Architecture):** Software Requirements Specification (SRS), state transition diagrams, and sequence flows.
4. **Stage 4 (App Implementation):** Flask backend logic, Jinja2 template components, and Bootstrap 5 frontend.
5. **Stage 5 (Data Security):** PBKDF2-SHA256 password hashing, HttpOnly session cookies, and CSRF token protection.
6. **Stage 6 (Automated Testing):** Modular Unit and Integration tests executed via `pytest`.
7. **Stage 7 (UI Automation):** Headless end-to-end browser tests executed via Selenium WebDriver.
8. **Stage 8 (Code Linting):** Flake8 quality gate ensuring PEP8 syntax compliance.
9. **Stage 9 (CI Automation):** Multi-stage Jenkins pipeline (`Jenkinsfile`) running on a local workspace.
10. **Stage 10 (Containerization):** Production Multi-Stage `Dockerfile` isolating app runtimes.
11. **Stage 11 (Image Security):** Non-root user allocation (`sprs`) and minimal runtime dependencies.
12. **Stage 12 (Registry Integration):** Versioned image tag publishing (`v1`, `build-N`) to Docker Hub (`5be4eb7d3ebdb885f/spare-parts-app`).
13. **Stage 13 (Configuration Management Script):** Complete Ansible playbook (`ansible/site.yml`) auditing local workspace prerequisites.
14. **Stage 14 (Automated Provisioning & Idempotency):** Double-run execution logging proving zero configuration drift (`changed=0`).
15. **Stage 15 (Final Release & Documentation):** Production technical reports, viva scripts, and final repository delivery.

---

## 🛠️ Configuration Management & Idempotency (Ansible)

To automate host provisioning without requiring manual setup steps, SPRS incorporates Ansible configuration management scripts in the `ansible/` directory.

### Ansible Execution Command:
```bash
ansible-playbook -i ansible/hosts ansible/site.yml
```

### Key Playbook Tasks (`ansible/site.yml`):
* **Workspace Structure Audit:** Validates presence and permissions (`0755`) for all core directories (`src`, `docker`, `jenkins`, `ansible`, `tests`).
* **Environment Verification:** Asserts Python runtime is $\ge 3.10$, verifies `venv` module availability, and checks `pip` readiness.
* **Toolchain Discovery:** Checks host environment for Docker Engine, Docker Compose v2, and Git.
* **Security & File Permission Hardening:**
  * Source code & configurations: Enforces `0644` (owner-writable, world-readable).
  * Sensitive data (`src/data.json`, `docker/.env`): Enforces `0600` (owner read-write only).
* **Git Hygiene:** Automatically populates and enforces local exclusion entries within `.gitignore`.

### Proof of Idempotency (Stage 14 Deliverable):
* **Initial Run:** Provisions missing directory rules or permissions $\rightarrow$ `changed=1`.
* **Second Run:** Audits an already-compliant workspace $\rightarrow$ **`changed=0`** (Proves script safety across repeated executions).

---

## 🚀 CI/CD Pipeline & Quality Gates (Jenkins)

The pipeline is managed via `jenkins/Jenkinsfile` and automates four strict stage gates:

```
+-------------------+      +--------------------+      +-----------------------+      +-----------------------+
|  Stage 1: Lint    | ---> |   Stage 2: Test    | ---> | Stage 3: Docker Build | ---> | Stage 4: Registry Push|
|  Flake8 Audit     |      | Pytest + Selenium  |      | Multi-Stage Container |      | Docker Hub Tagging    |
+-------------------+      +--------------------+      +-----------------------+      +-----------------------+
```

1. **Lint Stage:** Runs `flake8 --max-line-length=120` against Python sources. Fails build on syntax errors.
2. **Test Stage:** Launches temporary Flask instance on port `5055`, executes `pytest` suite, and runs 6 headless **Selenium browser tests** verifying UI rendering, role routing, and form submission flows.
3. **Containerization Stage:** Compiles application binary inside Docker multi-stage environment.
4. **Registry Push Stage:** Authenticates against Docker Hub using secure Jenkins credentials and tags images with `v1` and active `build-${BUILD_NUMBER}`.

---

## 🐳 Containerization & Deployment (Docker)

### Multi-Stage Dockerfile Strategy:
To optimize image size and secure runtime execution, SPRS uses a multi-stage Docker build:
* **Build Stage:** Installs compiler tools, builds wheel packages, and sets up dependencies.
* **Final Stage:** Copies pre-built wheels into a clean `python:3.12-slim` environment, creates a non-root system user `sprs` (UID 10001), and drops root privileges.

### Running with Docker Compose:
```bash
docker compose -f docker/docker-compose.yml up -d
```
Access the application on port `5000` with active volume mounts for `data.json` persistence.

---

## 💻 Local Installation & Setup Guide

### System Prerequisites:
* Python 3.10 or Python 3.12+
* Git
* Docker Desktop & WSL2 / Linux Terminal (for Ansible)

### Quick Step-by-Step Setup:

1. **Clone the repository:**
   ```bash
   git clone https://github.com/Shub-H4m430/spare-part-system.git
   cd spare-part-system
   ```

2. **Initialize Python Virtual Environment:**
   ```bash
   python -m venv venv
   # On Windows PowerShell:
   .\venv\Scripts\activate
   # On Linux / macOS / WSL:
   source venv/bin/activate
   ```

3. **Install Dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Launch the Application:**
   ```bash
   # Standard Mode:
   python src/app.py

   # Presentation / Demo Mode (enables one-click demo logins):
   python src/app.py --demo
   ```
   Open **`http://127.0.0.1:5000`** in your browser.

---

## 🧪 Automated Testing Suite

The project features comprehensive unit, integration, and UI test coverage.

### Running Pytest Unit & Integration Tests:
```bash
pytest tests/ -v
```

### Running Headless Selenium UI Tests:
```bash
pytest tests/selenium/test_spare_parts_ui.py -v
```

---

## 📁 Repository Structure

```text
spare-part-system/
├── .gitignore                  # Git tracking exclusions (managed by Ansible)
├── README.md                   # System documentation landing page
├── requirements.txt            # Python application dependencies
├── ansible/
│   ├── hosts                   # Ansible local inventory file
│   └── site.yml                # Configuration management playbook
├── docker/
│   ├── Dockerfile              # Secure multi-stage Docker build specification
│   ├── docker-compose.yml      # Container service orchestration file
│   └── .env                    # Runtime environment key-value pairs
├── docs/
│   ├── agile_plan.md           # Kanban backlog, user stories, MoSCoW matrix
│   ├── architecture.md        # Technical SRS, state diagrams, data model
│   ├── final_report.md         # Final release summary & troubleshooting guide
│   └── problem_statement.md    # Plant operational pain points analysis
├── jenkins/
│   └── Jenkinsfile             # Automated CI/CD build pipeline script
├── src/
│   ├── app.py                  # Core Flask application & business logic engine
│   ├── data.json               # Atomic JSON data store
│   └── templates/
│       └── index.html          # Unified Bootstrap 5 UI template
└── tests/
    ├── conftest.py             # Pytest fixtures and app factory helpers
    └── selenium/
        └── test_spare_parts_ui.py # End-to-end browser automation suite
```

---

## ❓ Troubleshooting Guide

| Issue / Symptom | Cause | Resolution |
| :--- | :--- | :--- |
| **`Address already in use: 5000`** | Port 5000 held by AirPlay or an orphaned process. | Change port via environment variable: `SPRS_PORT=5050 python src/app.py`. |
| **`ModuleNotFoundError: Flask`** | Virtual environment inactive or packages uninstalled. | Run `source venv/bin/activate` followed by `pip install -r requirements.txt`. |
| **`pip_check.rc == 0 Assertion Failed`** | Missing `pip` or `venv` package in WSL environment. | Run `sudo apt update && sudo apt install -y python3-pip python3-venv`. |
| **`Waiting for cache lock: dpkg`** | Ubuntu background update (`unattended-upgr`) active. | Wait 2 mins or terminate lock: `sudo kill <PID>` then `sudo rm /var/lib/dpkg/lock-frontend`. |
| **`Form session expired (CSRF)`** | Session secret mismatch post-server restart. | Refresh browser page (`Ctrl+F5`) to fetch fresh CSRF session tokens. |

---

## 🔮 Future Enhancements & Roadmap

* **Phase 1 (Production Hardening):** Deploy Gunicorn WSGI behind Nginx reverse proxy with TLS/HTTPS termination.
* **Phase 2 (Database Migration):** Replace `JsonStore` with PostgreSQL and SQLAlchemy ORM using `SELECT ... FOR UPDATE` row locking.
* **Phase 3 (Workflow Expansion):** Introduce Store Clerk roles for physical part issuance confirmation and Celery/Redis email notifications.
* **Phase 4 (Cloud Native Scaling):** Package application into Kubernetes Manifests (Helm charts) with Horizontal Pod Autoscalers (HPA) using `/health` probes.

---

## 📜 License & Credits

Developed as part of the **Spare Parts Request System (SPRS)** DevOps Academic Assignment. Distributed under open academic guidelines.