"""
TestAgent — Testing Reviewer
==============================
Analyses Python source files and their test files to identify testing gaps.

Checks performed:
  T-01  Missing test file for a source module
  T-02  Test file exists but contains no assertions
  T-03  Public function has no corresponding test function
  T-04  No edge-case / error-path tests detected
  T-05  Authentication logic present but no auth tests found
  T-06  No regression test markers found

Implements the same scan_directory(Path) -> list[Finding] interface
as Sentinel and Logic so it plugs straight into the Aggregator.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

from agents.sentinel import Finding


# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------

_AUTH_RE = re.compile(
    r"(login|logout|authenticate|authorize|token|jwt|oauth|permission|role|"
    r"password|credential|access_control|verify_token|require_auth)",
    re.IGNORECASE,
)
_EDGE_RE = re.compile(
    r"(invalid|empty|none|null|zero|negative|boundary|overflow|"
    r"error|exception|fail|raises|edge)",
    re.IGNORECASE,
)
_REGRESSION_RE = re.compile(
    r"(regression|bug|fix|issue|ticket|gh-\d+|#\d+)",
    re.IGNORECASE,
)
_TEST_DIRS = ("tests", "test")


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _is_test_file(path: Path) -> bool:
    return path.name.startswith("test_") or path.name.endswith(("_test.py", "_tests.py"))


def _find_test_file(source: Path, root: Path) -> Path | None:
    stem = source.stem
    candidates = [f"test_{stem}.py", f"{stem}_test.py", f"{stem}_tests.py"]
    for td in _TEST_DIRS:
        test_dir = root / td
        if not test_dir.is_dir():
            continue
        for c in candidates:
            p = test_dir / c
            if p.exists():
                return p
    return None


def _public_functions(path: Path) -> list[tuple[str, int]]:
    try:
        tree = ast.parse(_read(path))
    except SyntaxError:
        return []
    return [
        (n.name, n.lineno)
        for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        and not n.name.startswith("_")
    ]


def _test_function_names(test_file: Path) -> set[str]:
    try:
        tree = ast.parse(_read(test_file))
    except SyntaxError:
        return set()
    return {
        n.name
        for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        and n.name.startswith("test")
    }


def _has_assertions(test_file: Path) -> bool:
    src = _read(test_file)
    return bool(re.search(r"\bassert\b|\.assert[A-Z]|\bexpect\b", src))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def scan_file(path: Path, root: Path) -> list[Finding]:
    """Run all test-quality checks on a single source file."""
    findings: list[Finding] = []
    rel = str(path.relative_to(root))
    test_file = _find_test_file(path, root)

    # T-01 — missing test file
    if test_file is None:
        findings.append(Finding(
            agent="TestAgent",
            rule_id="T-01",
            severity="HIGH",
            file=rel,
            line=1,
            message=f"No test file found for '{path.name}'",
            snippet="",
            fix_hint=f"Create tests/test_{path.stem}.py with at least one test function.",
        ))
        return findings  # remaining checks need a test file

    # T-02 — no assertions
    if not _has_assertions(test_file):
        findings.append(Finding(
            agent="TestAgent",
            rule_id="T-02",
            severity="HIGH",
            file=str(test_file.relative_to(root)),
            line=1,
            message=f"Test file for '{path.name}' contains no assertions",
            snippet="",
            fix_hint="Add assert statements or pytest assertions to validate behaviour.",
        ))

    # T-03 — untested public functions
    test_names = _test_function_names(test_file)
    for fn_name, lineno in _public_functions(path):
        if not any(fn_name.lower() in t.lower() for t in test_names):
            findings.append(Finding(
                agent="TestAgent",
                rule_id="T-03",
                severity="MEDIUM",
                file=rel,
                line=lineno,
                message=f"Public function '{fn_name}' has no corresponding test",
                snippet=fn_name,
                fix_hint=f"Add a test function named 'test_{fn_name}' in the test file.",
            ))

    # T-04 — no edge-case tests
    test_src = _read(test_file)
    if not _EDGE_RE.search(test_src):
        findings.append(Finding(
            agent="TestAgent",
            rule_id="T-04",
            severity="MEDIUM",
            file=str(test_file.relative_to(root)),
            line=1,
            message=f"No edge-case or error-path tests detected for '{path.name}'",
            snippet="",
            fix_hint="Add tests for None inputs, empty collections, boundary values, and exceptions.",
        ))

    # T-05 — auth logic without auth tests
    src = _read(path)
    if _AUTH_RE.search(src) and not _AUTH_RE.search(test_src):
        findings.append(Finding(
            agent="TestAgent",
            rule_id="T-05",
            severity="HIGH",
            file=str(test_file.relative_to(root)),
            line=1,
            message=f"Authentication logic in '{path.name}' has no auth tests",
            snippet="",
            fix_hint="Add tests for successful auth, failed auth, invalid tokens, and expired tokens.",
        ))

    # T-06 — no regression markers
    if not _REGRESSION_RE.search(test_src):
        findings.append(Finding(
            agent="TestAgent",
            rule_id="T-06",
            severity="LOW",
            file=str(test_file.relative_to(root)),
            line=1,
            message=f"No regression test markers found for '{path.name}'",
            snippet="",
            fix_hint="Add a comment like '# Regression: GH-42' above relevant tests.",
        ))

    return findings


def scan_directory(directory: Path) -> list[Finding]:
    """Scan all non-test Python source files under `directory`."""
    root = directory
    all_findings: list[Finding] = []
    for py_file in sorted(directory.rglob("*.py")):
        if _is_test_file(py_file):
            continue
        if py_file.name == "__init__.py":
            continue
        if any(p in _TEST_DIRS for p in py_file.parts):
            continue
        all_findings.extend(scan_file(py_file, root))
    return all_findings
