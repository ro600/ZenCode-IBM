"""
Sentinel — Security Reviewer Agent
====================================
Analyses Python source files for security vulnerabilities.

Checks performed:
  S-01  Hardcoded secrets / credentials
  S-02  SQL injection via string interpolation
  S-03  Plain-text password storage / comparison
  S-04  Weak or missing JWT configuration
  S-05  Unauthenticated sensitive endpoints
"""
from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal


Severity = Literal["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"]


@dataclass
class Finding:
    agent: str
    rule_id: str
    severity: Severity
    file: str
    line: int
    message: str
    snippet: str = ""
    fix_hint: str = ""

    def to_dict(self) -> dict:
        return {
            "agent": self.agent,
            "rule_id": self.rule_id,
            "severity": self.severity,
            "file": self.file,
            "line": self.line,
            "message": self.message,
            "snippet": self.snippet,
            "fix_hint": self.fix_hint,
        }


# ---------------------------------------------------------------------------
# Pattern-based checks
# ---------------------------------------------------------------------------

_HARDCODED_SECRET_RE = re.compile(
    r'(secret|password|passwd|api_key|token|secret_key)\s*=\s*["\'][^"\']{4,}["\']',
    re.IGNORECASE,
)

_SQL_FSTRING_RE = re.compile(r'f["\'].*SELECT.*WHERE.*\{', re.IGNORECASE | re.DOTALL)

_PLAIN_PASSWORD_RE = re.compile(r'\.password\s*=\s*\w+\.password', re.IGNORECASE)


def _lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines()


def _check_hardcoded_secrets(path: Path, source_lines: list[str]) -> list[Finding]:
    findings: list[Finding] = []
    for i, line in enumerate(source_lines, 1):
        if _HARDCODED_SECRET_RE.search(line):
            findings.append(
                Finding(
                    agent="Sentinel",
                    rule_id="S-01",
                    severity="CRITICAL",
                    file=str(path),
                    line=i,
                    message="Hardcoded secret/credential detected",
                    snippet=line.strip(),
                    fix_hint="Move to environment variable: os.environ['SECRET_KEY']",
                )
            )
    return findings


def _check_sql_injection(path: Path, source_lines: list[str]) -> list[Finding]:
    findings: list[Finding] = []
    for i, line in enumerate(source_lines, 1):
        stripped = line.strip()
        # Detect f-string SQL with user-controlled variable interpolation
        if re.search(r'text\(f["\']', stripped) or re.search(r'execute\(f["\']', stripped):
            findings.append(
                Finding(
                    agent="Sentinel",
                    rule_id="S-02",
                    severity="CRITICAL",
                    file=str(path),
                    line=i,
                    message="SQL injection via f-string interpolation in query",
                    snippet=stripped,
                    fix_hint="Use parameterised queries: text('SELECT ... WHERE email = :email'), {'email': email}",
                )
            )
    return findings


def _check_plain_text_password(path: Path, source_lines: list[str]) -> list[Finding]:
    findings: list[Finding] = []
    for i, line in enumerate(source_lines, 1):
        stripped = line.strip()
        # password stored without hashing
        if re.search(r'password\s*=\s*\w+\.password\b', stripped, re.IGNORECASE):
            findings.append(
                Finding(
                    agent="Sentinel",
                    rule_id="S-03",
                    severity="HIGH",
                    file=str(path),
                    line=i,
                    message="Plain-text password assigned — must be hashed before storage",
                    snippet=stripped,
                    fix_hint="Use passlib: hashed = pwd_context.hash(password)",
                )
            )
        # plain-text password comparison
        if re.search(r'\.password\s*!=\s*password\b', stripped, re.IGNORECASE):
            findings.append(
                Finding(
                    agent="Sentinel",
                    rule_id="S-03",
                    severity="HIGH",
                    file=str(path),
                    line=i,
                    message="Plain-text password comparison — must verify against hash",
                    snippet=stripped,
                    fix_hint="Use: pwd_context.verify(plain_password, hashed_password)",
                )
            )
    return findings


def _check_weak_jwt(path: Path, source_lines: list[str]) -> list[Finding]:
    findings: list[Finding] = []
    for i, line in enumerate(source_lines, 1):
        stripped = line.strip()
        if re.search(r'SECRET_KEY\s*=\s*["\']', stripped):
            findings.append(
                Finding(
                    agent="Sentinel",
                    rule_id="S-04",
                    severity="CRITICAL",
                    file=str(path),
                    line=i,
                    message="JWT SECRET_KEY hardcoded in source",
                    snippet=stripped,
                    fix_hint="SECRET_KEY = os.environ['JWT_SECRET_KEY']",
                )
            )
    return findings


_ROUTE_DECORATOR_RE = re.compile(r'@app\.(get|post|put|patch|delete)\(')
_AUTH_DEPENDENCY_RE = re.compile(r'decode_access_token|Depends\(get_current_user\)')


def _check_unauthenticated_endpoints(path: Path, source_lines: list[str]) -> list[Finding]:
    """Detect route handlers that have no authentication dependency in their signature."""
    findings: list[Finding] = []
    n = len(source_lines)
    for i, line in enumerate(source_lines):
        stripped = line.strip()
        if _ROUTE_DECORATOR_RE.search(stripped):
            # Look ahead up to 5 lines to find the def statement and its signature
            for j in range(i + 1, min(i + 6, n)):
                sig_line = source_lines[j].strip()
                if sig_line.startswith("def ") or sig_line.startswith("async def "):
                    # Collect the full signature (may span multiple lines up to the colon)
                    sig = sig_line
                    k = j + 1
                    while ":" not in sig and k < min(j + 6, n):
                        sig += " " + source_lines[k].strip()
                        k += 1
                    if not _AUTH_DEPENDENCY_RE.search(sig):
                        findings.append(
                            Finding(
                                agent="Sentinel",
                                rule_id="S-05",
                                severity="HIGH",
                                file=str(path),
                                line=j + 1,  # 1-based
                                message="Route handler has no authentication dependency",
                                snippet=sig_line,
                                fix_hint="Add Depends(get_current_user) parameter or require decode_access_token",
                            )
                        )
                    break
    return findings


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def scan_file(path: Path) -> list[Finding]:
    """Run all security checks on a single Python file."""
    source_lines = _lines(path)
    findings: list[Finding] = []
    findings.extend(_check_hardcoded_secrets(path, source_lines))
    findings.extend(_check_sql_injection(path, source_lines))
    findings.extend(_check_plain_text_password(path, source_lines))
    findings.extend(_check_weak_jwt(path, source_lines))
    findings.extend(_check_unauthenticated_endpoints(path, source_lines))
    return findings


def scan_directory(directory: Path) -> list[Finding]:
    """Recursively scan all .py files under `directory`."""
    all_findings: list[Finding] = []
    for py_file in sorted(directory.rglob("*.py")):
        all_findings.extend(scan_file(py_file))
    return all_findings
