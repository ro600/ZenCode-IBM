# AGENTS.md — Agent Registry

> Maintained by Person 1 (Snehansha). Updated as agents are added/changed.

## Active Agents

### Sentinel *(Security Reviewer)*
- **File:** `agents/sentinel.py`
- **Owner:** Person 1
- **Role:** Scans Python source for security vulnerabilities
- **Rules:**
  | ID | Name | Severity |
  |----|------|----------|
  | S-01 | Hardcoded secret/credential | CRITICAL |
  | S-02 | SQL injection via f-string | CRITICAL |
  | S-03 | Plain-text password storage/comparison | HIGH |
  | S-04 | Weak/hardcoded JWT secret | CRITICAL |
  | S-05 | Unauthenticated sensitive endpoint | HIGH |

### Logic *(Correctness Reviewer)*
- **File:** `agents/logic.py`
- **Owner:** Person 1
- **Role:** Scans Python source for correctness/logic issues
- **Rules:**
  | ID | Name | Severity |
  |----|------|----------|
  | L-01 | Missing balance guard before transfer | HIGH |
  | L-02 | Division without zero guard | MEDIUM |
  | L-03 | Implicit None return where value expected | MEDIUM |
  | L-04 | Unhandled exception from jwt.decode | HIGH |

### Aggregator *(Review Aggregator)*
- **File:** `agents/aggregator.py`
- **Owner:** Person 1
- **Role:** Merges findings from all agents, classifies risk, produces report
- **Output:** `ReviewReport` with markdown + dict serialisation

### Fix Agent
- **File:** `agents/fix_agent.py`
- **Owner:** Person 1
- **Role:** Applies approved patches to source files for each rule_id

## Planned Agents (teammates)

| Agent | Owner | Status |
|-------|-------|--------|
| TestAgent | Person 2 | Planned |
| DocAgent | Person 3 | Planned |

## Agent Communication Protocol
1. Each agent exports `scan_directory(Path) -> list[Finding]`
2. `Finding` dataclass lives in `agents/sentinel.py` and is imported by all agents
3. Aggregator calls all agents and merges results
4. Fix Agent receives a list of approved rule_ids from the review report
