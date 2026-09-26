# PRISM Review Engine — Implementation Plan

## Overview

This plan covers the complete implementation of the PRISM (Parallel Review and Intelligent Security Monitor)
review engine, the FastAPI demo application, all review agents, the fix/approval workflow, the full test suite,
and all associated documentation. The project is a demonstration of IBM Bob orchestrating parallel AI subagents
to review, classify, and auto-fix code issues.

**Scope:** Person 1 responsibilities only.
**Goal:** A fully working, demo-ready system where Bob spawns Sentinel + Logic as subagents,
the Aggregator classifies findings, a human approves fixes, the Fix Agent applies patches, and
regression tests verify correctness.

**Non-goals:** TestAgent, DocAgent (teammate scope). Front-end UI. Production deployment hardening.

---

## Current State

All core files already exist and are functional. The work is primarily:
1. Filling known gaps (S-05 check, L-03 check, Bob orchestration entry point, integration test file)
2. Improving existing code where gaps were found
3. Ensuring docs are accurate and complete
4. Wiring everything together into a single runnable Bob workflow

### Files that already exist and are reused as-is
- `app/models.py` — ORM models (User, Transaction) — no changes needed
- `app/schemas.py` — Pydantic v2 schemas — no changes needed
- `app/database.py` — SQLAlchemy engine/session — no changes needed
- `app/main.py` — FastAPI routes — no changes needed (bugs are intentional)
- `app/crud.py` — business logic — no changes needed (bugs are intentional)
- `app/auth.py` — JWT utilities — no changes needed (bugs are intentional)
- `agents/sentinel.py` — Sentinel agent — minor extension (add S-05 check)
- `agents/logic.py` — Logic agent — minor extension (add L-03 check)
- `agents/aggregator.py` — ReviewReport + run_review — no changes needed
- `agents/fix_agent.py` — Fix workflow — no changes needed
- `tests/conftest.py` — shared fixtures — no changes needed
- `tests/test_baseline.py` — baseline tests — no changes needed
- `tests/test_regression.py` — regression tests — minor extension
- `docs/intentional_bugs.md` — bug catalogue — update for new rules
- `docs/prism_protocol.md` — protocol steps — review and confirm accurate
- `docs/security_review_process.md` — process doc — update for new rules
- `docs/architecture.md` — architecture — update for Bob orchestration entry point

### New files to create
- `agents/bob_orchestrator.py` — Bob-facing entry point; wraps run_review + apply_fixes into a single callable workflow
- `tests/test_integration.py` — end-to-end integration test: scan → report → fix → re-scan → regression suite

---

## Sub-Task 1 — Extend Sentinel with S-05 (Unauthenticated Sensitive Endpoint)

**Status:** [ ] pending

### Intent
S-05 is declared in the Sentinel docstring and rule catalogue but has no implementation.
The demo app has 8 endpoints and **none** require authentication, which is the exact scenario S-05 must flag.
Adding this check makes the demo more complete and ensures the rule catalogue matches the code.

### Expected Outcomes
- `_check_unauthenticated_endpoints(path, source_lines) -> list[Finding]` exists in `agents/sentinel.py`
- Rule S-05 with severity HIGH is emitted for each `@app.post`/`@app.get` decorated route that does not
  include `Depends(decode_access_token)` or similar auth dependency in its signature
- `scan_file` calls the new check
- Sentinel unit tests for S-05 are added to `tests/test_regression.py`
- `docs/security_review_process.md` S-05 row is filled in

### Todo List
- [ ] Add `_check_unauthenticated_endpoints` function in `agents/sentinel.py` after the existing checks
  - Pattern: detect `@app.post(` or `@app.get(` lines; look ahead for the function signature;
    flag if neither `decode_access_token` nor `Depends(get_current_user)` appears in the signature
  - Emit Finding with rule_id="S-05", severity="HIGH", fix_hint pointing to adding bearer token dependency
  - **Detection only — do NOT add S-05 to `_FIXES` registry** (fix requires middleware, architectural change)
- [ ] Add "S-05" to the `scan_file` call chain
- [ ] Add `test_sentinel_detects_unauthenticated_endpoint` unit test in `tests/test_regression.py`
  using a synthetic tmp_path file
- [ ] Update `docs/security_review_process.md` table row for S-05

### Relevant Context
- `agents/sentinel.py` `scan_file()` (line 166): add S-05 check call
- Pattern inspiration: existing `_check_hardcoded_secrets` function (line 67)
- Demo target: `/transfer` and `/users/{user_id}/summary` in `app/main.py` — neither has auth
- Detection should be line-by-line regex, consistent with existing pattern checks

---

## Sub-Task 2 — Extend Logic with L-03 (Implicit None Return)

**Status:** [ ] pending

### Intent
L-03 is declared in the Logic docstring but has no implementation. It catches functions that have
a non-None return type annotation but can return None implicitly (fall off the end without returning a value).
This is a real issue in `app/crud.py` — `login()` returns `None` implicitly when user is None,
and `divide_balance()` returns `0.0` (not None) but the pattern is worth detecting.

### Expected Outcomes
- `_check_implicit_none_return(path, source_lines) -> list[Finding]` exists in `agents/logic.py`
- Rule L-03 with severity MEDIUM is emitted for functions annotated `-> str` or `-> int` (non-optional)
  where the function body has a conditional early return that falls through without returning a value
- `scan_file` calls the new check
- Logic unit test for L-03 added to `tests/test_regression.py`
- `docs/security_review_process.md` L-03 row is filled in

### Todo List
- [ ] Add `_check_implicit_none_return` in `agents/logic.py` after the existing checks
  - Pattern: detect `def ...) -> str:` or `-> int:` (not `-> ... | None:` and not `-> Optional[...]`)
    where the function body contains a conditional `return None` or ends without a return statement
  - A practical simplification: flag functions with `-> str` annotation that contain `return None`
    (explicit None return from a non-Optional function)
  - Emit Finding with rule_id="L-03", severity="MEDIUM", fix_hint suggesting explicit return or type annotation change
- [ ] Add "L-03" to the `scan_file` call chain in `agents/logic.py`
- [ ] Add `test_logic_detects_implicit_none_return` unit test in `tests/test_regression.py`
- [ ] Update `docs/security_review_process.md` table row for L-03

### Relevant Context
- `agents/logic.py` `scan_file()` (line 121): add L-03 check call
- Existing pattern: `_check_division_zero` (line 65) for style reference
- Target in app: `login()` in `app/crud.py` returns `None` but is typed `-> str | None`
  (this is actually correct typing, so the check should focus on non-Optional annotated functions)

---

## Sub-Task 3 — Bob Orchestrator Entry Point

**Status:** [ ] pending

### Intent
Currently there is no single entry point that Bob's Agent mode can call to run the full PRISM workflow:
scan → present report → wait for approval → apply fixes → re-scan → verify tests.
This sub-task creates `agents/bob_orchestrator.py` — a thin wrapper that Bob executes in Agent mode,
making the entire pipeline callable with a single function. This is the glue between the Python agents
and the IBM Bob demonstration.

### Expected Outcomes
- `agents/bob_orchestrator.py` exists with a `run_prism_workflow(target_dir, repo_root, approved_rule_ids)` function
- The function is **two-phase**: phase 1 (scan only, `approved_rule_ids=None`) returns the report;
  phase 2 (with `approved_rule_ids`) applies fixes, re-scans, and returns a before/after comparison dict
- An **interactive CLI** `main()` wraps the two-phase API: prints the report, prompts the user to select
  rule_ids, then calls phase 2. Run with `python -m agents.bob_orchestrator app/`
- The module docstring explains Bob Agent mode usage: Bob calls phase 1, presents `to_markdown()` in chat,
  waits for the developer to reply with approved rule_ids, then calls phase 2

### Todo List
- [ ] Create `agents/bob_orchestrator.py` with:
  - Module docstring explaining Bob Agent mode integration
  - `run_prism_workflow(target_dir: Path, repo_root: Path, approved_rule_ids: list[str] | None = None) -> dict`
    that returns `{"pre_fix_report": ..., "fixes_applied": ..., "post_fix_report": ..., "regression_clean": ...}`
  - `main()` CLI function using `argparse` or `sys.argv` for `target_dir` argument
  - `if __name__ == "__main__": main()`
- [ ] Add `bob_orchestrator` to the Active Agents table in `AGENTS.md`

### Relevant Context
- `agents/aggregator.py` `run_review(target_dir)` (line 101): primary call
- `agents/fix_agent.py` `apply_fixes(rule_ids, repo_root)` (line 127): fix call
- `docs/architecture.md` "Data Flow" section (line 74): describes this 10-step process
- README.md "Run a Review" section shows manual usage pattern

---

## Sub-Task 4 — Integration Test Suite

**Status:** [ ] pending

### Intent
There are baseline tests (`test_baseline.py`) and regression tests (`test_regression.py`) but no
end-to-end integration test that exercises the full PRISM pipeline in sequence:
run_review → verify findings → apply_all_fixes → re-scan → verify zero findings → run regression suite.
This integration test is critical for the demo — it proves the entire workflow works end-to-end.

### Expected Outcomes
- `tests/test_integration.py` exists with tests covering the complete pipeline
- Tests use the `app/` directory (not tmp_path), scanning real intentional bugs
- A test verifies: pre-fix scan finds 7+ issues, `blocks_merge=True`
- A test verifies: after `apply_all_fixes`, re-scan finds 0 CRITICAL/HIGH issues, `blocks_merge=False`
- Tests are isolated — they operate on copies of app files (tmp_path copies) so they don't permanently
  alter the demo app (or they reset via git after the test)
- Alternatively, tests work on the live `app/` but are clearly marked as mutating and must be run after
  baseline tests and before regression tests

### Todo List
- [ ] Create `tests/test_integration.py` with:
  - `test_full_pipeline_pre_fix`: Calls `run_review(Path("app/"))`, asserts ≥7 findings, asserts `blocks_merge=True`,
    asserts CRITICAL findings exist (S-01, S-02, S-04)
  - `test_full_pipeline_report_format`: Verifies `ReviewReport.to_markdown()` contains expected headers and findings,
    `to_dict()` contains `total`, `blocks_merge`, `by_severity`, `findings` keys
  - `test_fix_workflow_apply_and_verify`:
    - Calls `apply_all_fixes(Path("."))` on the live `app/` files
    - Re-runs `run_review(Path("app/"))` and asserts `blocks_merge=False`
    - **Precondition: test must run on a clean git state; `git restore app/` restores the demo bugs after the run**
  - `test_bob_orchestrator_workflow`: Calls `run_prism_workflow` phase 1 (scan only) end-to-end
- [ ] Add a module docstring explaining that this test mutates `app/` and requires `git restore app/` afterwards

### Relevant Context
- `agents/aggregator.py` `run_review()` (line 101)
- `agents/fix_agent.py` `apply_all_fixes()` (line 149)
- `tests/conftest.py` — `db_engine` is session-scoped; integration tests don't need the DB fixtures
- Important: fix functions alter source files in-place; tests must use tmp_path copies to avoid
  permanently modifying the demo codebase

---

## Sub-Task 5 — Documentation Completeness Pass

**Status:** [ ] pending

### Intent
The four docs files exist but some sections are incomplete or inconsistent with the code:
- `security_review_process.md` is missing S-05 and L-03 rows
- `architecture.md` doesn't mention `bob_orchestrator.py`
- `intentional_bugs.md` doesn't mention S-05 as a detected issue (since all endpoints are unauthenticated)
- `prism_protocol.md` is accurate and needs only minor updates

### Expected Outcomes
- All four docs files accurately reflect the implemented code
- `security_review_process.md` has complete tables for all rules (S-01–S-05, L-01–L-04)
- `architecture.md` mentions `bob_orchestrator.py` in the directory structure and data flow sections
- `intentional_bugs.md` mentions that the entire app has unauthenticated endpoints (S-05)
- `prism_protocol.md` confirms fix approval model matches `apply_fixes(rule_ids, repo_root)`

### Todo List
- [ ] Update `docs/security_review_process.md`:
  - Add S-05 row to Security Review Checks table
  - Add L-03 row to Correctness Review Checks table
- [ ] Update `docs/architecture.md`:
  - Add `bob_orchestrator.py` to directory structure listing
  - Add note about Bob calling `run_prism_workflow` in the Data Flow section
- [ ] Update `docs/intentional_bugs.md`:
  - Add note that all endpoints lack authentication (S-05 detectable across all routes)
- [ ] Review `docs/prism_protocol.md` against actual code; correct any inconsistencies

### Relevant Context
- `docs/security_review_process.md` (line 21): Checks table ends at S-04
- `docs/architecture.md` (line 34): Directory structure listing
- `docs/intentional_bugs.md` (line 6): Bug catalogue table

---

## Sub-Task 6 — Final Validation

**Status:** [ ] pending

### Intent
Run the complete test suite to verify all baseline and regression tests pass, the integration test
passes, and the entire pipeline executes cleanly end-to-end.

### Expected Outcomes
- `pytest tests/test_baseline.py -v` — all 12 tests pass
- `pytest tests/test_regression.py -v` — all 20+ tests pass
- `pytest tests/test_integration.py -v` — all integration tests pass
- `python -m agents.bob_orchestrator app/` runs cleanly and prints a review report
- No regressions introduced by S-05 and L-03 additions

### Todo List
- [ ] Run `pytest tests/ -v` and confirm all tests pass
- [ ] Run `python -m agents.bob_orchestrator app/` and confirm readable output
- [ ] Confirm no new false positives from S-05/L-03 in tests/ or agents/ directories
  (scan_directory is always called with `app/`, not repo root, so this should be clean)

### Relevant Context
- `AGENTS.md` commands section has run instructions
- Test database file `test_prism.db` persists at repo root — may need manual deletion if schema changes

---

## Architecture Overview

### Component Map

```
IBM Bob (Agent mode)
  └── agents/bob_orchestrator.py
        ├── run_prism_workflow(target_dir, repo_root, approved_rule_ids)
        │     ├── [1] run_review(target_dir)  ← agents/aggregator.py
        │     │         ├── sentinel_scan(target_dir)  ← agents/sentinel.py
        │     │         │     ├── S-01: Hardcoded secrets
        │     │         │     ├── S-02: SQL injection
        │     │         │     ├── S-03: Plain-text password
        │     │         │     ├── S-04: Weak JWT secret
        │     │         │     └── S-05: Unauthenticated endpoint [NEW]
        │     │         └── logic_scan(target_dir)  ← agents/logic.py
        │     │               ├── L-01: Missing balance guard
        │     │               ├── L-02: Division without zero guard
        │     │               ├── L-03: Implicit None return [NEW]
        │     │               └── L-04: Unhandled jwt.decode
        │     ├── [2] Present ReviewReport to developer (Bob chat)
        │     ├── [3] Receive approved_rule_ids from developer
        │     ├── [4] apply_fixes(approved_rule_ids, repo_root)  ← agents/fix_agent.py
        │     └── [5] re-run run_review → verify clean
        │
        └── FastAPI Demo App (app/)
              ├── app/main.py       — 8 endpoints (all intentionally unauthed)
              ├── app/crud.py       — business logic (5 intentional bugs)
              ├── app/auth.py       — JWT (2 intentional bugs)
              ├── app/models.py     — User, Transaction ORM models
              ├── app/schemas.py    — Pydantic v2 request/response
              └── app/database.py  — SQLite engine + session factory
```

### Fix Registry (agents/fix_agent.py)

| Rule | File | Fix Function |
|------|------|-------------|
| S-01 | app/auth.py | fix_s01_s04_hardcoded_secret |
| S-02 | app/crud.py | fix_s02_sql_injection |
| S-03 | app/crud.py | fix_s03_plain_text_password |
| S-04 | app/auth.py | fix_s01_s04_hardcoded_secret (shared) |
| L-01 | app/crud.py | fix_l01_balance_guard |
| L-02 | app/crud.py | fix_l02_division_zero |
| L-04 | app/auth.py | fix_l04_unhandled_jwt |
| S-05 | — | No fix (S-05 requires architectural change; demo only detects) |
| L-03 | — | No fix (advisory; detection only) |

### Severity / Risk Matrix

| Severity | Rules | Merge Policy |
|----------|-------|-------------|
| CRITICAL | S-01, S-02, S-04 | Must fix before merge |
| HIGH | S-03, S-05, L-01, L-04 | Should fix before merge |
| MEDIUM | L-02, L-03 | Fix before next release |
| LOW/INFO | — | Advisory |

`ReviewReport.blocks_merge` is `True` when any CRITICAL or HIGH finding is present.

### Test Strategy

| File | Scope | State | Asserts |
|------|-------|-------|---------|
| `test_baseline.py` | API + DB | Buggy app | Broken behavior (200 on overdraft, 500 on /divide?divisor=0) |
| `test_regression.py` | Agents + API | Post-fix | Fixed behavior + zero agent findings |
| `test_integration.py` (NEW) | Full pipeline | Buggy → Fixed | Scan finds 7+; fix all; re-scan finds 0; blocks_merge=False |

### IBM Bob Integration

Bob runs in **Agent mode** and uses `spawn_subagent` to run Sentinel and Logic in parallel.
In the current implementation (`agents/aggregator.py` comment: "sequential here for simplicity"),
both are called sequentially. The `bob_orchestrator.py` entry point documents how Bob would
replace the sequential calls with `spawn_subagent` calls.

Bob's conversational approval step:
1. Bob calls `run_prism_workflow(Path("app/"), Path("."), approved_rule_ids=None)`
2. Bob presents the `ReviewReport.to_markdown()` to the developer in chat
3. Developer replies with which rule_ids to approve
4. Bob calls `run_prism_workflow(Path("app/"), Path("."), approved_rule_ids=[...])`

---

## File Change Summary

| File | Action | Change |
|------|--------|--------|
| `agents/sentinel.py` | Modify | Add S-05 check function + call in scan_file |
| `agents/logic.py` | Modify | Add L-03 check function + call in scan_file |
| `agents/bob_orchestrator.py` | Create | Full PRISM workflow entry point for Bob |
| `tests/test_regression.py` | Modify | Add S-05 and L-03 unit tests |
| `tests/test_integration.py` | Create | End-to-end pipeline integration tests |
| `docs/security_review_process.md` | Modify | Add S-05 and L-03 rows |
| `docs/architecture.md` | Modify | Add bob_orchestrator.py to structure + data flow |
| `docs/intentional_bugs.md` | Modify | Note S-05 (all endpoints unauthed) |
| `docs/prism_protocol.md` | Modify | Minor consistency fixes if needed |
| `AGENTS.md` | Modify | Add bob_orchestrator to Active Agents table |
| All `app/` files | No change | Intentional bugs preserved |
| `agents/aggregator.py` | No change | Already complete |
| `agents/fix_agent.py` | No change | Already complete |
| `tests/test_baseline.py` | No change | Already complete |
| `tests/conftest.py` | No change | Already complete |
