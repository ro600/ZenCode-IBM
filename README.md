# Bob PR Guardian — PRISM Review System

> **P**arallel **R**eview and **I**ntelligent **S**ecurity **M**onitor

An AI-powered Pull Request reviewer and auto-fixer built on IBM Bob.

---

## Architecture

```
PR / Code Changes
       │
       ▼
IBM Bob Agent
       │
┌──────┼──────────────┐
▼      ▼      ▼       ▼
Sentinel  Logic  TestAgent  DocAgent
       │
       ▼
Review Aggregator ──► Dashboard (Flask UI)
       │
  ┌────┴────┐
  ▼         ▼
Report   Auto Fix → Run Tests
```

---

## Agents

### Person 1 — Snehansha (Security & Logic)

| Agent | File | Role |
|-------|------|------|
| **Sentinel** | `agents/sentinel.py` | Security review — secrets, SQL injection, auth |
| **Logic** | `agents/logic.py` | Correctness — null handling, edge cases |
| **Aggregator** | `agents/aggregator.py` | Merges findings, classifies severity |
| **Fix Agent** | `agents/fix_agent.py` | Applies approved patches, reruns tests |

### Person 2 — Aaryan (Testing & Docs + Dashboard)

| Component | Location | Description |
|-----------|----------|-------------|
| **TestAgent** | `agents/test_agent.py` | Testing reviewer — finds missing tests and coverage gaps |
| **DocAgent** | `agents/doc_agent.py` | Documentation reviewer — finds doc/code inconsistencies |
| **Shared Models** | `prism/models.py` | `Finding`, `ReviewResult`, enums shared by all reviewers |
| **Aggregator** | `prism/dashboard/aggregator.py` | Merges reviewer outputs into `DashboardState` |
| **Dashboard App** | `prism/dashboard/app.py` | Flask web app + REST API |
| **Dashboard UI** | `prism/dashboard/templates/` & `static/` | HTML/CSS/JS single-page interface |

---

## Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Run the FastAPI app (Snehansha)

```bash
uvicorn app.main:app --reload
```

### 3. Run the Dashboard (Aaryan)

```bash
python run_dashboard.py
```

Open **http://localhost:5000** in your browser.

### 4. Point the dashboard at a specific repository

```bash
PRISM_REPO_ROOT=/path/to/repo \
PRISM_REPO="org/repo" \
PRISM_PR="#42" \
PRISM_BRANCH="feature/my-pr" \
python run_dashboard.py
```

---

## Run Tests

```bash
pytest tests/ -v
```

---

## Run a Review (CLI)

```python
from pathlib import Path
from agents.aggregator import run_review

report = run_review(Path("app/"))
print(report.to_markdown())
```

## Apply Fixes

```python
from pathlib import Path
from agents.fix_agent import apply_all_fixes

results = apply_all_fixes(Path("."))
print(results)
```

---

## Intentional Bugs (Demo PR)

The base app contains **7 intentional issues** for the demo:

| # | ID | Severity | Issue |
|---|-----|----------|-------|
| 1 | L-01 | HIGH | No balance check before transfer |
| 2 | S-03 | HIGH | Plain-text password storage |
| 3 | S-01 | CRITICAL | Hardcoded JWT secret |
| 4 | S-04 | CRITICAL | Weak JWT configuration |
| 5 | S-02 | CRITICAL | SQL injection in email lookup |
| 6 | L-02 | MEDIUM | Division by zero (no guard) |
| 7 | L-04 | HIGH | Unhandled jwt.decode exception |

See [`docs/intentional_bugs.md`](docs/intentional_bugs.md) for full details.

---

## Repository Structure

```
agents/
├── sentinel.py         # Security reviewer (Snehansha)
├── logic.py            # Logic reviewer (Snehansha)
├── aggregator.py       # Review aggregator (Snehansha)
├── fix_agent.py        # Auto-fixer (Snehansha)
├── test_agent.py       # Testing reviewer (Aaryan)
└── doc_agent.py        # Docs reviewer (Aaryan)
app/
├── main.py             # FastAPI entry point
├── models.py           # ORM models (intentional bugs)
├── crud.py             # Business logic
├── auth.py             # JWT auth
├── schemas.py          # Pydantic schemas
└── database.py         # DB setup
prism/
├── models.py           # Shared Finding / ReviewResult models (Aaryan)
├── reviewers/
│   ├── test_pilot.py   # TestPilot reviewer (Aaryan)
│   └── docs_guard.py   # DocsGuard reviewer (Aaryan)
└── dashboard/
    ├── aggregator.py   # Aggregator + DashboardState (Aaryan)
    ├── app.py          # Flask app + REST API (Aaryan)
    ├── templates/      # Dashboard HTML
    └── static/         # Dashboard CSS/JS
tests/
├── conftest.py
├── test_baseline.py
└── test_regression.py
requirements.txt
run_dashboard.py
```

---

## Docs

- [`docs/architecture.md`](docs/architecture.md)
- [`docs/prism_protocol.md`](docs/prism_protocol.md)
- [`docs/security_review_process.md`](docs/security_review_process.md)
- [`docs/aaryan.md`](docs/aaryan.md)
- [`AGENTS.md`](AGENTS.md)

---

## Environment Variables (Dashboard)

| Variable | Default | Description |
|----------|---------|-------------|
| `PRISM_REPO_ROOT` | `.` | Path to the repository being reviewed |
| `PRISM_PORT` | `5000` | Dashboard port |
| `PRISM_REPO` | `""` | Repository name displayed in the UI |
| `PRISM_PR` | `""` | Pull request identifier |
| `PRISM_BRANCH` | `""` | Branch name |
| `PRISM_AUTHOR` | `""` | PR author name |
