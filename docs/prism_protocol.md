# PRISM Review Protocol

**P**arallel **R**eview and **I**ntelligent **S**ecurity **M**onitor

## Overview

PRISM is the review protocol used by Bob PR Guardian. It defines how code changes
are analysed, classified, and fixed before merging.

## Protocol Steps

### Step 1 — Trigger
A developer submits a PR or points Bob at a directory of changed files.

### Step 2 — Parallel Agent Scan (Person 1 scope)
Bob launches Sentinel and Logic as parallel subagents:

```
IBM Bob
  ├─ spawn_subagent(Sentinel) → security findings
  └─ spawn_subagent(Logic)    → correctness findings
```

### Step 3 — Aggregation
The Review Aggregator:
1. Collects findings from both agents
2. Deduplicates by (file, line, rule_id)
3. Sorts by severity (CRITICAL → HIGH → MEDIUM → LOW → INFO)
4. Determines merge-blocking status (any CRITICAL or HIGH = blocked)
5. Emits a `ReviewReport` as Markdown + JSON

### Step 4 — Review Report
The report is presented to the developer showing:
- Total finding count
- Severity breakdown
- Per-finding: file, line, code snippet, fix hint

### Step 5 — Fix Approval
The developer reviews the report and approves fixes (all or selective).

### Step 6 — Fix Application
The Fix Agent:
1. Applies each approved fix via pattern replacement
2. Re-runs Sentinel + Logic to verify zero remaining findings
3. Runs the full test suite

### Step 7 — Regression Verification
Tests must all pass before the review is marked ✅ APPROVED.

## Severity Classification

| Level | Definition | Merge Policy |
|-------|-----------|--------------|
| CRITICAL | Data breach / immediate exploit | Must fix before merge |
| HIGH | Logic error / exploitable with effort | Should fix before merge |
| MEDIUM | Edge case / degraded functionality | Fix before next release |
| LOW | Minor style / advisory | Fix at discretion |
| INFO | Informational | No action required |

## Rule Catalogue

See [AGENTS.md](../AGENTS.md) for the full rule catalogue maintained by each agent owner.
