# PRISM Person 2 — Component Reference

This document is the canonical reference for the Person 2 components:
TestPilot, DocsGuard, Aggregator, and the PRISM Dashboard.

See [README.md](../README.md) for the project overview and quick-start guide.

---

## Finding data model

All reviewers share the `Finding` dataclass defined in `prism/models.py`.

```python
@dataclass
class Finding:
    id: str                                # e.g. "TEST-001", "DOCS-003"
    category: Category                     # bug | security | testing | documentation
    severity: Severity                     # critical | high | medium | low | info
    title: str                             # Short, human-readable title
    description: str                       # Full explanation
    file: Optional[str]                    # Relative path of the affected file
    line: Optional[int]                    # Line number within the file
    evidence: Optional[str]               # What triggered the finding
    suggested_fix: Optional[str]          # Concrete fix recommendation
    fix_recommendation: Optional[str]     # Broader guidance
    requires_human_approval: bool         # True → must not be auto-applied
    status: FindingStatus                  # open | approved | rejected | fixed | pending_review
```

### Status transitions

```
open ──► approved ──► fixed
     ──► rejected
     ──► pending_review ──► approved / rejected
```

Use the helper methods on `Finding`:

```python
finding.approve()        # → approved
finding.reject()         # → rejected
finding.mark_fixed()     # → fixed
finding.flag_for_review() # → pending_review + requires_human_approval = True
```

---

## TestPilot — detection logic

| Check | Severity | Triggered when |
|-------|----------|----------------|
| Missing test file | HIGH | No `test_<name>.py` or `<name>_test.py` found |
| No assertions | HIGH | Test file has no `assert` / `assertX` / `expect` |
| Untested function | MEDIUM | Public fn name not found in any test function name |
| No edge-case tests | MEDIUM | Test file has no edge/error/boundary vocabulary |
| Missing auth tests | HIGH | Source has auth keywords, test file does not |
| No regression tests | LOW | No regression/bug/fix/issue keywords in test file |

Finding IDs are assigned sequentially: `TEST-001`, `TEST-002`, …

---

## DocsGuard — detection logic

| Check | Severity | Triggered when |
|-------|----------|----------------|
| No README | HIGH | None of the expected doc files exist |
| Broken file reference | MEDIUM | Doc mentions `` `file.py` `` that does not exist |
| Doc endpoint not implemented | HIGH | `GET /path` in docs but no matching route decorator |
| Impl route not documented | MEDIUM | Route decorator found but no docs mention it |
| Missing function docstring | LOW | Public function has no docstring (AST check) |
| Missing class docstring | LOW | Public class has no docstring (AST check) |

Finding IDs are assigned sequentially: `DOCS-001`, `DOCS-002`, …

Supported route decorator patterns:

- `@app.get("/path")` / `@app.post(...)` — Flask/FastAPI
- `@router.get("/path")` — FastAPI router
- `@blueprint.route("/path")` — Flask Blueprint
- `@bp.get("/path")` — Flask Blueprint shorthand

---

## Aggregator

`prism/dashboard/aggregator.py`

### DashboardState properties

| Property | Type | Description |
|----------|------|-------------|
| `total_findings` | int | All findings across all reviewers |
| `open_findings` | list | Status == open |
| `approved_findings` | list | Status == approved |
| `rejected_findings` | list | Status == rejected |
| `fixed_findings` | list | Status == fixed |
| `pending_findings` | list | Status == pending_review |
| `requires_human_review` | list | `requires_human_approval == True` |
| `overall_risk` | str | Highest severity among open findings |
| `review_status` | str | pending / in_progress / blocked / complete |
| `bug_count` | int | Findings with category == bug |
| `security_count` | int | Findings with category == security |
| `testing_count` | int | Findings with category == testing |
| `docs_count` | int | Findings with category == documentation |

### DashboardState.final_results()

Returns a dict with:

```python
{
    "findings_before": int,        # total findings
    "findings_after":  int,        # remaining open findings
    "fixes_applied":   int,        # approved + fixed
    "tests_generated": None,       # populated by Person 1 runner
    "tests_passed":    None,       # populated by Person 1 runner
    "tests_failed":    None,       # populated by Person 1 runner
    "final_pr_status": str,        # review_status value
}
```

The `tests_*` fields are `None` until Person 1's test-runner integration
provides them.  The dashboard displays "—" for `None` values.

---

## Dashboard REST API

Base URL: `http://localhost:5000`

### `GET /api/state`

Returns the full `DashboardState` serialised as JSON.

```json
{
  "pr": { "repository": "org/repo", "pull_request": "#42", ... },
  "review_status": "in_progress",
  "overall_risk": "high",
  "total_findings": 14,
  "summary": { "bugs": 0, "security": 0, "testing": 9, "documentation": 5 },
  "findings": [ { "id": "TEST-001", ... }, ... ],
  "final_results": { ... }
}
```

### `POST /api/refresh`

Re-runs TestPilot and DocsGuard and returns a fresh state object.

### `POST /api/findings/<id>/approve`

Approve the fix for a finding.  Returns `{ "id": "...", "status": "approved" }`.

### `POST /api/findings/<id>/reject`

Reject the fix for a finding.  Returns `{ "id": "...", "status": "rejected" }`.

### `POST /api/findings/<id>/fix`

Mark a finding as fixed.  Returns `{ "id": "...", "status": "fixed" }`.

### `GET /api/results`

Returns the `final_results` dict.

---

## Dashboard UI

The browser UI is a single HTML page (`dashboard.html`) driven by
`dashboard.js`.  It communicates with the Flask API and does not
contain hardcoded review data.

### Panels

| Panel | Content |
|-------|---------|
| **PR Overview** | Repository, PR, branch, review status badge, risk badge, total findings |
| **Finding Summary** | Counts by category (Bugs / Security / Testing / Documentation) |
| **Findings** | Filterable list with Approve / Reject controls per finding |
| **Final Results** | Before/after counts, fixes applied, test runner stats, final PR status |

### Finding card status colours

| Status | Left border colour |
|--------|--------------------|
| `open` | Grey |
| `approved` | Green |
| `rejected` | Red |
| `fixed` | Blue |
| `pending_review` | Amber |

Findings with `requires_human_approval = true` display an amber
**"👁 Human Review"** badge.

---

## Integration notes for Person 1

To plug Sentinel / Logic results into the dashboard:

```python
# In prism/dashboard/app.py — inside _build_state():
from prism.reviewers.sentinel import Sentinel  # Person 1
from prism.reviewers.logic    import Logic     # Person 1

agg.add_result(Sentinel(root=repo_root).review())
agg.add_result(Logic(root=repo_root).review())
```

Each reviewer only needs to return a `ReviewResult` with a list of
`Finding` objects from `prism.models`.

If Person 1's finding schema differs, a thin adapter in `aggregator.py`
can translate it — the dashboard is completely decoupled from individual
reviewer implementations.
