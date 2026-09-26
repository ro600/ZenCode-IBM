# PRISM — PR Intelligent Security Monitor

PRISM is an automated pull-request review system that runs multiple specialised
reviewers against a repository, aggregates their findings, and presents them
through an interactive dashboard.

---

## Aaryan Scope — Components Implemented

| Component | Location | Description |
|-----------|----------|-------------|
| **Shared Models** | `prism/models.py` | `Finding`, `ReviewResult`, enums shared by all reviewers |
| **TestPilot** | `prism/reviewers/test_pilot.py` | Testing reviewer — finds missing tests and coverage gaps |
| **DocsGuard** | `prism/reviewers/docs_guard.py` | Documentation reviewer — finds doc/code inconsistencies |
| **Aggregator** | `prism/dashboard/aggregator.py` | Merges reviewer outputs into `DashboardState` |
| **Dashboard App** | `prism/dashboard/app.py` | Flask web app + REST API |
| **Dashboard UI** | `prism/dashboard/templates/` & `static/` | HTML/CSS/JS single-page interface |

---

## Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Run the dashboard

```bash
python run_dashboard.py
```

Open **http://localhost:5000** in your browser.

### 3. Point at a specific repository

```bash
PRISM_REPO_ROOT=/path/to/repo \
PRISM_REPO="org/repo" \
PRISM_PR="#42" \
PRISM_BRANCH="feature/my-pr" \
python run_dashboard.py
```

---

## Architecture

```
┌──────────────┐   ReviewResult   ┌─────────────┐   DashboardState   ┌───────────┐
│  TestPilot   │ ───────────────► │             │ ─────────────────► │ Dashboard │
├──────────────┤                  │  Aggregator │                     │   (UI)    │
│  DocsGuard   │ ───────────────► │             │                     └───────────┘
├──────────────┤                  └─────────────┘
│  Sentinel *  │  (* Person 1)
├──────────────┤
│  Logic    *  │  (* Person 1)
└──────────────┘
```

All reviewers produce `ReviewResult` objects containing `Finding` items.
The `Aggregator` merges them.  The dashboard reads only from the `Aggregator`.

---

## Finding Structure

```json
{
  "id": "TEST-001",
  "category": "testing",
  "severity": "high",
  "title": "No test file for auth.py",
  "description": "No corresponding test file was found for 'auth.py'.",
  "file": "prism/auth.py",
  "line": null,
  "evidence": "Searched for test_auth.py / auth_test.py in test directories.",
  "suggested_fix": "Create tests/test_auth.py and add unit tests.",
  "fix_recommendation": "Add a test file with at least happy-path and error-path tests.",
  "requires_human_approval": false,
  "status": "open"
}
```

### Categories

| Value | Description |
|-------|-------------|
| `bug` | Logic errors or incorrect behaviour |
| `security` | Security vulnerabilities or missing controls |
| `testing` | Missing or insufficient test coverage |
| `documentation` | Docs missing, inaccurate, or out of sync with code |

### Severities

`critical` → `high` → `medium` → `low` → `info`

### Statuses

| Value | Meaning |
|-------|---------|
| `open` | Finding not yet actioned |
| `approved` | Fix approved by a reviewer |
| `rejected` | Fix rejected |
| `fixed` | Applied and verified |
| `pending_review` | Awaiting human decision |

---

## Components

### TestPilot

Static analysis reviewer that identifies test quality issues.

**Checks performed:**
- Missing test file for a source module
- Test file present but contains no assertions
- Public functions with no corresponding test
- No edge-case / error-path tests detected
- Authentication logic without authentication tests
- No regression tests present

**Usage:**
```python
from prism.reviewers import TestPilot

result = TestPilot(root="/path/to/repo").review()
for finding in result.findings:
    print(finding.id, finding.severity, finding.title)
```

**Constructor parameters:**

| Parameter | Default | Description |
|-----------|---------|-------------|
| `root` | `"."` | Repository root to scan |
| `source_dirs` | `["src","app","lib","prism","."]` | Source directories |
| `test_dirs` | `["tests","test"]` | Test directories |

---

### DocsGuard

Static analysis reviewer that identifies documentation inconsistencies.

**Checks performed:**
- No README or documentation file found
- Documentation references a file that does not exist
- Documented API endpoint not found in source code
- Implemented route not mentioned in documentation
- Public functions missing docstrings
- Public classes missing docstrings

**Usage:**
```python
from prism.reviewers import DocsGuard

result = DocsGuard(root="/path/to/repo").review()
for finding in result.findings:
    print(finding.id, finding.severity, finding.title)
```

**Constructor parameters:**

| Parameter | Default | Description |
|-----------|---------|-------------|
| `root` | `"."` | Repository root to scan |
| `doc_files` | `["README.md", "docs/api.md", ...]` | Documentation files to check |

---

### Aggregator

Merges `ReviewResult` objects from all reviewers into a single `DashboardState`.

```python
from prism.dashboard import Aggregator, PRMetadata
from prism.reviewers import TestPilot, DocsGuard

pr = PRMetadata(repository="org/repo", pull_request="#42")
agg = Aggregator(pr=pr)
agg.add_result(TestPilot(root=".").review())
agg.add_result(DocsGuard(root=".").review())
state = agg.build()

print(state.total_findings)
print(state.overall_risk)
print(state.review_status)
```

**Integration with Person 1 reviewers:**

```python
# Person 1's Sentinel and Logic reviewers produce ReviewResult objects
# of the same shape — just add them to the Aggregator:
agg.add_result(sentinel_result)
agg.add_result(logic_result)
```

---

### Dashboard

A Flask web application with a REST API and a browser-based UI.

#### REST API

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/` | Dashboard HTML page |
| `GET` | `/api/state` | Full `DashboardState` as JSON |
| `POST` | `/api/refresh` | Re-run all reviewers, return fresh state |
| `POST` | `/api/findings/<id>/approve` | Approve a finding fix |
| `POST` | `/api/findings/<id>/reject` | Reject a finding fix |
| `POST` | `/api/findings/<id>/fix` | Mark a finding as fixed |
| `GET` | `/api/results` | Final results summary |

#### Programmatic usage

```python
from prism.dashboard import create_app, PRMetadata

app = create_app(
    repo_root="/path/to/repo",
    pr_metadata=PRMetadata(repository="org/repo", pull_request="#42"),
)
app.run(port=5000)
```

---

## Integration with Person 1

Person 1 reviewers (Sentinel, Logic) should:

1. Return a `ReviewResult` object from `prism.models`.
2. Populate it with `Finding` objects using the shared enums.
3. Pass the result to `Aggregator.add_result()`.

No changes to Aaryan's code are required for this integration.

If Person 1 has already defined a different `Finding` schema, the
`Aggregator` can be extended with an adapter — the dashboard only
consumes `DashboardState.to_dict()` and is schema-agnostic.

---

## Repository Structure (Aaryan files)

```
prism/
├── __init__.py
├── models.py                   # Shared Finding / ReviewResult models
├── reviewers/
│   ├── __init__.py
│   ├── test_pilot.py           # TestPilot reviewer
│   └── docs_guard.py           # DocsGuard reviewer
└── dashboard/
    ├── __init__.py
    ├── aggregator.py            # Aggregator + DashboardState
    ├── app.py                   # Flask app + REST API
    ├── templates/
    │   └── dashboard.html       # Dashboard SPA
    └── static/
        ├── dashboard.css        # Styles
        └── dashboard.js         # Frontend logic

requirements.txt
run_dashboard.py
README.md
docs/
└── aaryan.md                    # This document (component reference)
```

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PRISM_REPO_ROOT` | `.` | Path to the repository being reviewed |
| `PRISM_PORT` | `5000` | Dashboard port |
| `PRISM_REPO` | `""` | Repository name displayed in the UI |
| `PRISM_PR` | `""` | Pull request identifier |
| `PRISM_BRANCH` | `""` | Branch name |
| `PRISM_AUTHOR` | `""` | PR author name |
