# AGENTS.md

This file provides guidance to agents when working with code in this repository.

> Maintained by Person 1 (Snehansha). Updated as agents are added/changed.

## Project Overview

**PRISM** — Parallel Review and Intelligent Security Monitor. A FastAPI demo app with intentional bugs, plus a set of AI review agents that detect and patch those bugs.

## Stack

- **Backend:** FastAPI + SQLAlchemy (SQLite) + python-jose (JWT) + passlib (sha256_crypt)
- **Test framework:** pytest + pytest-asyncio + FastAPI `TestClient`
- **Python:** 3.x, all files use `from __future__ import annotations`

## Commands

```bash
# Install
pip install -r requirements.txt

# Run dev server
uvicorn app.main:app --reload

# Run all tests
pytest tests/ -v

# Run a single test
pytest tests/test_baseline.py::test_health -v

# Run baseline tests only (buggy state)
pytest tests/test_baseline.py -v

# Run regression tests only (post-fix state)
pytest tests/test_regression.py -v
```

## Critical Architecture Notes

- **`Finding` dataclass lives exclusively in `agents/sentinel.py`** — all other agents import it from there. Never redefine it elsewhere.
- Every agent exposes exactly **`scan_file(Path) -> list[Finding]`** and **`scan_directory(Path) -> list[Finding]`** as its public API.
- `scan_directory` uses `path.rglob("*.py")` — it recurses into `agents/` and `tests/` too. Pass `app/` (not repo root) when scanning only application code.
- **Fix functions in `agents/fix_agent.py` are string-literal replacements** — they match exact comment markers like `# BUG-1:`, `# BUG-2:`, `# BUG-3:` etc. If those comment strings are removed or changed, `apply_fixes` silently returns `False` and does nothing.
- `S-01` and `S-04` share the same fix function (`fix_s01_s04_hardcoded_secret`) targeting `app/auth.py`.

## Test Database

- Tests use a **separate SQLite file** (`test_prism.db` at repo root); production uses `prism.db`.
- `db_engine` fixture is **session-scoped** (created once per pytest run); `db_session` and `client` are **function-scoped**. User IDs from one test do not carry over to another because each test gets a fresh session — but the schema persists for the whole run.
- Use `client_no_raise` fixture (not `client`) to test endpoints that intentionally crash with 500.
- Tests override `app.dependency_overrides[get_db]` in conftest; always call `app.dependency_overrides.clear()` after the test (handled by fixtures — do not add extra overrides without clearing).

## Intentional Bugs (Demo — do not remove unless fixing)

The `app/` directory intentionally contains 7 bugs used for the demo:

| Bug ID | Rule | File | Description |
|--------|------|------|-------------|
| BUG-1 | L-01 | `app/crud.py` | `transfer_funds` — no balance check before debit |
| BUG-2 | S-03 | `app/crud.py` | Plain-text password storage and comparison |
| BUG-3 | S-01 | `app/auth.py` | Hardcoded `SECRET_KEY` string |
| BUG-4 | S-04/L-04 | `app/auth.py` | Weak JWT + unhandled `jwt.decode` exception |
| BUG-5 | S-02 | `app/crud.py` | f-string SQL injection in `get_user_by_email` |
| BUG-6 | L-02 | `app/crud.py` | `divide_balance` — no zero-division guard |
| BUG-7 | — | `app/crud.py` | Misleading docstring (returns `dict`, not JSON) |

`test_baseline.py` tests **assert broken behaviour** (e.g. 200 on overdraft). Do not "fix" those assertions.

## Code Style

- Module docstrings list intentional issues at the top (`Intentional Issues:` block) — preserve these in `app/`.
- All type annotations use `from __future__ import annotations` (PEP 563 postponed evaluation).
- Pydantic v2 schemas use `model_config = {"from_attributes": True}` (not the v1 `orm_mode`).
- SQLAlchemy queries use the ORM (`db.query(Model).filter(...)`) except for the intentional raw SQL bug in `crud.get_user_by_email`.
- `app/database.py` uses `DeclarativeBase` (SQLAlchemy 2.x style), not the legacy `declarative_base()`.

## Agent Communication Protocol

1. Each agent exports `scan_directory(Path) -> list[Finding]`
2. `Finding` dataclass lives in `agents/sentinel.py` and is imported by all agents
3. Aggregator calls all agents and merges results (deduplicates by `(file, line, rule_id)`)
4. Fix Agent receives a list of approved `rule_id`s from the review report

## Active Agents

| Agent | File | Role |
|-------|------|------|
| Sentinel | `agents/sentinel.py` | Security: S-01–S-05 |
| Logic | `agents/logic.py` | Correctness: L-01–L-04 |
| Aggregator | `agents/aggregator.py` | Merges findings → `ReviewReport` |
| Fix Agent | `agents/fix_agent.py` | Applies patches keyed by `rule_id` |
| Bob Orchestrator | `agents/bob_orchestrator.py` | Bob entry point: scan → report → approve → fix → verify |

