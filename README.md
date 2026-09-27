# PreVise - AI-Powered PR Review System

> **Pre**dictive **Vi**sual **Se**curity Engine · Built on IBM Bob

PreVise is an end-to-end AI pull request reviewer that catches security vulnerabilities, logic bugs, testing gaps, and documentation drift - before code ships. It runs a multi-agent pipeline, surfaces findings in a live dashboard, and applies auto-fixes with a re-scan gate.

---

## Architecture

```
PR / Code Changes
       │
       ▼
IBM Bob Orchestrator  (agents/bob_orchestrator.py)
       │
┌──────┼──────────────┬───────────┐
▼      ▼              ▼           ▼
Sentinel  Logic    TestAgent   DocAgent
(S-01…05) (L-01…04) (T-01…06)  (D-01…06)
       │
       ▼
Review Aggregator ──► ReviewReport (Markdown + JSON)
       │
  ┌────┴────┐
  ▼         ▼
Report   Fix Agent → Re-scan → pytest gate
                │
                ▼
         PreVise Dashboard  (Flask · http://localhost:5000)
```

---

## Agents

### Security & Logic - Snehansha

| Agent | File | Checks |
|-------|------|--------|
| **Sentinel** | `agents/sentinel.py` | S-01 Hardcoded secrets · S-02 SQL injection · S-03 Plain-text passwords · S-04 Weak JWT · S-05 Unauthenticated endpoints |
| **Logic** | `agents/logic.py` | L-01 Missing balance guard · L-02 Division by zero · L-03 Implicit None return · L-04 Unhandled JWT decode |
| **Aggregator** | `agents/aggregator.py` | Merges findings, deduplicates, classifies severity, produces `ReviewReport` |
| **Fix Agent** | `agents/fix_agent.py` | Applies approved patches keyed by rule ID, re-scans to confirm clean |
| **Orchestrator** | `agents/bob_orchestrator.py` | CLI + programmatic entry point for the full scan → fix → verify pipeline |

### Testing & Docs + Dashboard - Aaryan

| Component | File | Role |
|-----------|------|------|
| **TestPilot** | `prism/reviewers/test_pilot.py` | T-01 Missing test file · T-02 No assertions · T-03 Untested functions · T-04 No edge cases · T-05 Missing auth tests · T-06 No regression markers |
| **DocsGuard** | `prism/reviewers/docs_guard.py` | D-01 No README · D-02 Broken file references · D-03 Documented route missing · D-04 Undocumented route · D-05 Missing function docstring · D-06 Missing class docstring |
| **Shared Models** | `prism/models.py` | `Finding`, `ReviewResult`, `Severity`, `Category`, `FindingStatus` enums |
| **Dashboard Aggregator** | `prism/dashboard/aggregator.py` | `Aggregator`, `DashboardState`, `PRMetadata`, `final_results()` |
| **Dashboard App** | `prism/dashboard/app.py` | Flask app + REST API (`/api/state`, `/api/refresh`, `/api/configure`, `/api/findings/:id/approve|reject|fix`, `/api/results`) |
| **Dashboard UI** | `prism/dashboard/templates/` & `static/` | PreVise live review dashboard |

---

## Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Run the FastAPI demo app

```bash
uvicorn app.main:app --reload
```

Open **http://127.0.0.1:8000/docs** for the interactive Swagger UI.

### 3. Run the PreVise Dashboard

```bash
# Activate your virtual environment first
.\.venv\Scripts\Activate.ps1          # Windows
source .venv/bin/activate             # macOS / Linux

python run_dashboard.py
```

Open **http://localhost:5000** in your browser.

### 4. Point the dashboard at a specific repository

```bash
PRISM_REPO_ROOT=/path/to/repo \
PRISM_REPO="org/repo"         \
PRISM_PR="#42"                \
PRISM_BRANCH="feature/my-pr"  \
python run_dashboard.py
```

---

## Run Tests

```bash
pytest tests/ -v
```

Expected: **94 passed, 1 xfailed** (the xfail is the intentional BUG-1 baseline test, which is expected to fail when fixes are applied).

---

## Agent CLI - Scan & Fix

**Scan only (read-only report):**
```bash
python -m agents.bob_orchestrator app/
```

**Scan and auto-fix all CRITICAL/HIGH findings:**
```bash
python -m agents.bob_orchestrator app/ --fix
```

**Scan, fix specific rules, then run regression tests:**
```bash
python -m agents.bob_orchestrator app/ --fix S-01 S-02 L-01 --run-tests
```

**Programmatic API:**
```python
from pathlib import Path
from agents.aggregator import run_review
from agents.fix_agent import apply_all_fixes

report = run_review(Path("app/"))
print(report.to_markdown())

results = apply_all_fixes(Path("."))
print(results)
```

---

## Dashboard REST API

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET`  | `/api/state` | Full `DashboardState` as JSON |
| `POST` | `/api/refresh` | Re-run all agents, return fresh state |
| `POST` | `/api/configure` | Set repo path + PR metadata, rebuild state |
| `POST` | `/api/findings/<id>/approve` | Approve a finding fix |
| `POST` | `/api/findings/<id>/reject` | Reject a finding fix |
| `POST` | `/api/findings/<id>/fix` | Mark a finding as fixed |
| `GET`  | `/api/results` | Final results summary |

---

## Intentional Bugs (Demo)

The `app/` directory contains **7 intentional bugs** used to demonstrate the full review pipeline:

| # | Rule | Severity | File | Description |
|---|------|----------|------|-------------|
| 1 | L-01 | HIGH | `app/crud.py` | `transfer_funds` - no balance check before debit |
| 2 | S-03 | HIGH | `app/crud.py` | Plain-text password storage and comparison |
| 3 | S-01 | CRITICAL | `app/auth.py` | `SECRET_KEY` hardcoded in source |
| 4 | S-04 | CRITICAL | `app/auth.py` | Weak JWT + hardcoded HS256 key |
| 5 | S-02 | CRITICAL | `app/crud.py` | SQL injection via f-string in `get_user_by_email` |
| 6 | L-02 | MEDIUM | `app/crud.py` | `divide_balance` - no zero-division guard |
| 7 | L-04 | HIGH | `app/auth.py` | `decode_access_token` - unhandled `jwt.decode` exception |

See [`docs/intentional_bugs.md`](docs/intentional_bugs.md) for full details and fix descriptions.

---

## Repository Structure

```
agents/
├── sentinel.py         # Security reviewer - S-01…S-05
├── logic.py            # Logic reviewer - L-01…L-04
├── aggregator.py       # Aggregates findings → ReviewReport
├── fix_agent.py        # Applies approved patches
├── bob_orchestrator.py # CLI + programmatic pipeline entry point
├── test_agent.py       # Testing reviewer - T-01…T-06
└── doc_agent.py        # Docs reviewer - D-01…D-06
app/
├── main.py             # FastAPI routes
├── crud.py             # Business logic (intentional bugs)
├── auth.py             # JWT auth (intentional bugs)
├── models.py           # SQLAlchemy ORM models
├── schemas.py          # Pydantic request/response schemas
└── database.py         # SQLite engine + session factory
prism/
├── models.py           # Shared Finding / ReviewResult / enums
├── reviewers/
│   ├── test_pilot.py   # TestPilot reviewer
│   └── docs_guard.py   # DocsGuard reviewer
└── dashboard/
    ├── aggregator.py   # DashboardState + Aggregator
    ├── app.py          # Flask app + REST API
    ├── templates/      # Dashboard HTML
    └── static/         # Dashboard CSS / JS
tests/
├── conftest.py         # Shared pytest fixtures + TestClient setup
├── test_baseline.py    # Baseline tests - document pre-fix behaviour
├── test_regression.py  # Regression tests - pass after fixes applied
├── test_integration.py # End-to-end scan → fix → rescan workflow
└── test_prism_reviewers.py  # Unit tests for prism/* components
run_dashboard.py        # Dashboard launcher
requirements.txt        # Python dependencies
AGENTS.md               # Agent registry + coding rules
```

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PRISM_REPO_ROOT` | `.` | Path to the repository to scan |
| `PRISM_PORT` | `5000` | Dashboard port |
| `PRISM_REPO` | `""` | Repository name shown in the UI |
| `PRISM_PR` | `""` | Pull request identifier |
| `PRISM_BRANCH` | `""` | Branch name |
| `PRISM_AUTHOR` | `""` | PR author name |
| `JWT_SECRET_KEY` | `changeme-in-production` | Secret key for JWT signing |

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Demo API | FastAPI 0.111 + SQLAlchemy 2.0 + SQLite |
| Auth | python-jose (JWT) + passlib (bcrypt) |
| Dashboard | Flask 3.x + vanilla JS |
| Testing | pytest 8.2 + pytest-asyncio + httpx |
| AI Orchestration | IBM Bob |

---

## Docs

- [`docs/architecture.md`](docs/architecture.md) - system architecture & data flow
- [`docs/intentional_bugs.md`](docs/intentional_bugs.md) - full bug catalogue with fixes
- [`docs/prism_protocol.md`](docs/prism_protocol.md) - review protocol
- [`docs/security_review_process.md`](docs/security_review_process.md) - security & logic review process
- [`docs/aaryan.md`](docs/aaryan.md) - dashboard & reviewer components
- [`AGENTS.md`](AGENTS.md) - agent registry + coding rules
