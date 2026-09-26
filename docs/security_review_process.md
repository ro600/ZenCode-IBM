# Security & Correctness Review Process

## Overview

This document describes how the Sentinel (security) and Logic (correctness)
agents review code changes, and how the Fix Agent applies approved patches.

---

## Security Review (Sentinel)

### Process

1. Sentinel receives a target directory path
2. It iterates every `.py` file using `scan_directory(path)`
3. Each file is passed through 4 pattern-based checks (S-01 through S-04)
4. Findings are returned as `list[Finding]` with severity, file, line, snippet, and fix hint

### Checks

| Rule | Check | Pattern |
|------|-------|---------|
| S-01 | Hardcoded credentials | `(secret|password|api_key)` `=` literal string |
| S-02 | SQL injection | `text(f"...{var}...")` or `execute(f"...")` |
| S-03 | Plain-text password | `user.password != password` or `password = user_in.password` |
| S-04 | Weak JWT secret | `SECRET_KEY = "..."` literal in source |
| S-05 | Unauthenticated endpoint | `@app.get/post(` decorator followed by `def` with no `Depends(get_current_user)` or `decode_access_token` in signature |

### Findings Format

```python
Finding(
    agent="Sentinel",
    rule_id="S-02",
    severity="CRITICAL",
    file="app/crud.py",
    line=42,
    message="SQL injection via f-string interpolation",
    snippet="query = text(f\"SELECT * FROM users WHERE email = '{email}'\")",
    fix_hint="Use parameterised queries: text('...WHERE email = :email'), {'email': email}",
)
```

---

## Correctness Review (Logic)

### Process

1. Logic agent receives a target directory path
2. It iterates every `.py` file using `scan_directory(path)`
3. Each file is passed through 4 checks (L-01 through L-04)
4. Findings are returned as `list[Finding]` with severity, file, line, snippet, and fix hint

### Checks

| Rule | Check | Pattern |
|------|-------|---------|
| L-01 | Missing balance guard | `def transfer_funds` with `sender.balance -=` but no prior `sender.balance < amount` |
| L-02 | Division without zero guard | `/ divisor` with no `if divisor == 0` in nearby context |
| L-03 | Implicit None return | Function annotated `-> T` (non-Optional) containing explicit `return None` |
| L-04 | Unhandled jwt.decode | `jwt.decode(` not wrapped in `try:` block |

---

## Fix / Approval Workflow

### Step 1 — Review Report
The Aggregator produces a `ReviewReport` with all findings sorted by severity.

### Step 2 — Developer Approval
Developer reviews the report and selects which rule_ids to fix:
```python
approved_rules = ["S-01", "S-02", "S-03", "S-04", "L-01", "L-02", "L-04"]
```

### Step 3 — Fix Application
```python
from agents.fix_agent import apply_fixes
from pathlib import Path

results = apply_fixes(approved_rules, repo_root=Path("."))
# Returns: {"S-01": True, "S-02": True, ...}
```

### Step 4 — Re-scan
After fixes are applied, Sentinel + Logic are re-run. Expected result:
```
Total findings: 0
Merge blocked: NO ✅
```

### Step 5 — Regression Tests
```bash
pytest tests/test_regression.py -v
```
All regression tests must pass.

---

## Intentional Bugs Catalogue

See [`intentional_bugs.md`](intentional_bugs.md) for the full list of demo bugs.
