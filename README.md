# Bob PR Guardian — PRISM Review System

> **P**arallel **R**eview and **I**ntelligent **S**ecurity **M**onitor

An AI-powered Pull Request reviewer and auto-fixer built on IBM Bob.

## Architecture

```
PR / Code Changes
       │
       ▼
IBM Bob Agent
       │
┌──────┼──────┐
▼      ▼      ▼
Sentinel  Logic  (+ Doc/Test agents — teammates)
       │
       ▼
Review Aggregator
       │
  ┌────┴────┐
  ▼         ▼
Report   Auto Fix → Run Tests
```

## Agents (Person 1 scope)

| Agent | File | Role |
|-------|------|------|
| **Sentinel** | `agents/sentinel.py` | Security review — secrets, SQL injection, auth |
| **Logic** | `agents/logic.py` | Correctness — null handling, edge cases |
| **Aggregator** | `agents/aggregator.py` | Merges findings, classifies severity |
| **Fix Agent** | `agents/fix_agent.py` | Applies approved patches, reruns tests |

## Quick Start

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
```

## Run Tests

```bash
pytest tests/ -v
```

## Run a Review

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

## Intentional Bugs (Demo PR)

The base app contains **7 intentional issues**:

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

## Docs

- [`docs/architecture.md`](docs/architecture.md)
- [`docs/prism_protocol.md`](docs/prism_protocol.md)
- [`docs/security_review_process.md`](docs/security_review_process.md)
- [`AGENTS.md`](AGENTS.md)
