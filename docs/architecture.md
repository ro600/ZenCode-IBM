# System Architecture

## Component Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                      FastAPI Application                     │
│  POST /users  GET /users/:id  POST /login  POST /transfer   │
│  POST /users/:id/transactions  GET /users/:id/summary       │
└──────────────────────────┬──────────────────────────────────┘
                           │ SQLAlchemy ORM
                           ▼
                     SQLite Database
                     (prism.db / test_prism.db)

┌─────────────────────────────────────────────────────────────┐
│                     PRISM Review Pipeline                    │
│                                                             │
│   IBM Bob (Orchestrator)                                    │
│         │                                                   │
│   ┌─────┴──────┐                                           │
│   ▼            ▼                                            │
│ Sentinel      Logic          (+ TestAgent, DocAgent)        │
│ (Security)  (Correctness)                                   │
│   └─────┬──────┘                                           │
│         ▼                                                   │
│    Aggregator  ──► ReviewReport (Markdown + JSON)          │
│         │                                                   │
│    Fix Agent  ──► applies patches ──► re-scan ──► tests    │
└─────────────────────────────────────────────────────────────┘
```

## Directory Structure

```
ZenCode-IBM/
├── app/
│   ├── main.py          FastAPI routes
│   ├── models.py        SQLAlchemy ORM models
│   ├── schemas.py       Pydantic request/response schemas
│   ├── crud.py          Business logic (contains intentional bugs)
│   ├── auth.py          JWT utilities (contains intentional bugs)
│   └── database.py      SQLite engine + session factory
├── agents/
│   ├── sentinel.py         Security Reviewer agent
│   ├── logic.py            Correctness Reviewer agent
│   ├── aggregator.py       Review Aggregator
│   ├── fix_agent.py        Fix Workflow agent
│   └── bob_orchestrator.py Bob entry point — run_prism_workflow() + CLI
├── tests/
│   ├── conftest.py      Shared pytest fixtures
│   ├── test_baseline.py Baseline tests (documents buggy behaviour)
│   └── test_regression.py Regression tests (pass after fixes)
├── docs/
│   ├── architecture.md  This file
│   ├── prism_protocol.md PRISM review protocol
│   ├── security_review_process.md Security + correctness process
│   └── intentional_bugs.md Catalogue of demo bugs
├── AGENTS.md            Agent registry
├── README.md            Project overview
└── requirements.txt     Python dependencies
```

## Technology Stack

| Layer | Technology |
|-------|-----------|
| Web framework | FastAPI 0.111 |
| ORM | SQLAlchemy 2.0 |
| Database | SQLite (dev) |
| Auth | python-jose (JWT) + passlib (sha256_crypt) |
| Testing | pytest + pytest-asyncio + httpx |
| AI orchestration | IBM Bob + subagents |

## Data Flow — Review Pipeline

1. Bob receives PR diff or target directory path
2. Bob calls `run_prism_workflow(target_dir, repo_root)` in `agents/bob_orchestrator.py`
3. Orchestrator calls `run_review(target_dir)` — spawns Sentinel and Logic (parallel in full demo)
4. Both agents return `list[Finding]`
5. Aggregator deduplicates and classifies by severity
6. `ReviewReport` is generated in Markdown + JSON and presented in Bob chat
7. Developer approves rule IDs to fix
8. Orchestrator calls `apply_fixes(approved_rule_ids, repo_root)`
9. Fix Agent applies patches; re-scan confirms zero findings
10. pytest runs full test suite
11. PR is approved if all tests pass and `blocks_merge` is False
