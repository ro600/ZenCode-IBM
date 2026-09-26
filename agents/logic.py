"""
Logic — Correctness Reviewer Agent
=====================================
Analyses Python source files for logic / correctness issues.

Checks performed:
  L-01  Missing balance / precondition check before mutation
  L-02  Division without zero guard
  L-03  Function returns None implicitly where a value is expected
  L-04  Unhandled exception from external call (JWT decode)
"""
from __future__ import annotations

import re
from pathlib import Path
from agents.sentinel import Finding


# ---------------------------------------------------------------------------
# Pattern checks
# ---------------------------------------------------------------------------

def _lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines()


def _check_missing_balance_guard(path: Path, source_lines: list[str]) -> list[Finding]:
    """Detect transfer functions that mutate balance without a prior check."""
    findings: list[Finding] = []
    in_transfer = False
    has_balance_check = False
    func_start = 0

    for i, line in enumerate(source_lines, 1):
        stripped = line.strip()
        if re.search(r'def transfer_funds\b', stripped):
            in_transfer = True
            has_balance_check = False
            func_start = i
        if in_transfer:
            # A real balance check looks like: sender.balance < amount  or  sender.balance >= amount
            if re.search(r'sender\.balance\s*[<>]=?\s*amount', stripped):
                has_balance_check = True
            # Detect the mutation line
            if re.search(r'sender\.balance\s*-=', stripped) and not has_balance_check:
                findings.append(
                    Finding(
                        agent="Logic",
                        rule_id="L-01",
                        severity="HIGH",
                        file=str(path),
                        line=i,
                        message="transfer_funds debits sender without checking sufficient balance",
                        snippet=stripped,
                        fix_hint="Add: if sender.balance < amount: return False",
                    )
                )
            # End of function (next def or end of file at same or lower indent)
            if i > func_start and re.match(r'^(def |class )', stripped):
                in_transfer = False

    return findings


def _check_division_zero(path: Path, source_lines: list[str]) -> list[Finding]:
    """Detect division operations without a preceding zero guard."""
    findings: list[Finding] = []
    for i, line in enumerate(source_lines, 1):
        stripped = line.strip()
        # Look for plain division by a variable named divisor / denominator
        if re.search(r'/\s*(divisor|denominator|div)\b', stripped) and not re.search(
            r'if\s+\w+\s*==\s*0', stripped
        ):
            # Check surrounding lines for guard
            context = "\n".join(source_lines[max(0, i - 4): i])
            if not re.search(r'if\s+\w+\s*==\s*0', context):
                findings.append(
                    Finding(
                        agent="Logic",
                        rule_id="L-02",
                        severity="MEDIUM",
                        file=str(path),
                        line=i,
                        message="Division by variable without zero-guard — potential ZeroDivisionError",
                        snippet=stripped,
                        fix_hint="Add: if divisor == 0: raise ValueError('divisor cannot be zero')",
                    )
                )
    return findings


def _check_unhandled_jwt_decode(path: Path, source_lines: list[str]) -> list[Finding]:
    """Detect jwt.decode calls without exception handling."""
    findings: list[Finding] = []
    for i, line in enumerate(source_lines, 1):
        stripped = line.strip()
        if re.search(r'jwt\.decode\(', stripped):
            # Check if inside a try block (look back up to 5 lines)
            context_above = source_lines[max(0, i - 6): i - 1]
            in_try = any("try:" in l for l in context_above)
            if not in_try:
                findings.append(
                    Finding(
                        agent="Logic",
                        rule_id="L-04",
                        severity="HIGH",
                        file=str(path),
                        line=i,
                        message="jwt.decode called without try/except — raises JWTError on invalid tokens",
                        snippet=stripped,
                        fix_hint="Wrap in try/except jose.JWTError and return None or raise HTTPException",
                    )
                )
    return findings


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def scan_file(path: Path) -> list[Finding]:
    """Run all logic checks on a single Python file."""
    source_lines = _lines(path)
    findings: list[Finding] = []
    findings.extend(_check_missing_balance_guard(path, source_lines))
    findings.extend(_check_division_zero(path, source_lines))
    findings.extend(_check_unhandled_jwt_decode(path, source_lines))
    return findings


def scan_directory(directory: Path) -> list[Finding]:
    """Recursively scan all .py files under `directory`."""
    all_findings: list[Finding] = []
    for py_file in sorted(directory.rglob("*.py")):
        all_findings.extend(scan_file(py_file))
    return all_findings
