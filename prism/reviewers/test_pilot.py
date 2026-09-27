"""
TestPilot — PRISM Testing Reviewer

Analyses source files and their corresponding test files to identify:
- Missing tests for source modules/functions
- Insufficient test coverage signals (no assertions, trivial bodies)
- Missing edge-case tests (no boundary / error-path tests)
- Missing authentication tests
- Missing regression markers
- Important functionality with no corresponding test

TestPilot does NOT run code or import target modules.  It performs
static analysis of the file tree and source text.
"""

from __future__ import annotations

import ast
import os
import re
from pathlib import Path
from typing import Optional

from prism.models import (
    Category,
    Finding,
    FindingStatus,
    ReviewResult,
    Severity,
)

# ------------------------------------------------------------------ #
# Heuristics                                                           #
# ------------------------------------------------------------------ #

# Function names that strongly suggest auth / access-control logic
_AUTH_PATTERNS = re.compile(
    r"(login|logout|authenticate|authorize|token|jwt|oauth|permission|role|"
    r"password|credential|access_control|verify_token|require_auth)",
    re.IGNORECASE,
)

# Patterns that suggest edge-case / error-path coverage
_EDGE_PATTERNS = re.compile(
    r"(invalid|empty|none|null|zero|negative|boundary|overflow|"
    r"error|exception|fail|raises|edge)",
    re.IGNORECASE,
)

# Patterns that suggest regression tests
_REGRESSION_PATTERNS = re.compile(
    r"(regression|bug|fix|issue|ticket|gh-\d+|#\d+)",
    re.IGNORECASE,
)

# Common test-file naming conventions
_TEST_FILE_SUFFIXES = ("_test.py", "_tests.py")
_TEST_FILE_PREFIXES = ("test_",)


def _is_test_file(path: Path) -> bool:
    name = path.name
    return name.startswith(_TEST_FILE_PREFIXES) or name.endswith(_TEST_FILE_SUFFIXES)


def _find_test_file(source: Path, test_dirs: list[Path]) -> Optional[Path]:
    """Return the test file that corresponds to *source*, or None."""
    stem = source.stem
    candidates = [
        f"test_{stem}.py",
        f"{stem}_test.py",
        f"{stem}_tests.py",
    ]
    for test_dir in test_dirs:
        for candidate in candidates:
            p = test_dir / candidate
            if p.exists():
                return p
    return None


def _collect_public_functions(source: Path) -> list[tuple[str, int]]:
    """Return list of (function_name, lineno) for top-level public functions."""
    try:
        tree = ast.parse(source.read_text(encoding="utf-8", errors="replace"))
    except SyntaxError:
        return []
    results = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if not node.name.startswith("_"):
                results.append((node.name, node.lineno))
    return results


def _collect_test_function_names(test_file: Path) -> set[str]:
    """Return set of test function names in a test file."""
    try:
        tree = ast.parse(test_file.read_text(encoding="utf-8", errors="replace"))
    except SyntaxError:
        return set()
    return {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name.startswith("test")
    }


def _has_assertions(test_file: Path) -> bool:
    """Return True if the test file contains at least one assert-like call."""
    try:
        source = test_file.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return True  # can't tell — assume ok
    return bool(
        re.search(r"\bassert\b|\.assert[A-Z]|\bexpect\b", source)
    )


def _source_has_auth(source: Path) -> bool:
    try:
        return bool(_AUTH_PATTERNS.search(source.read_text(encoding="utf-8", errors="replace")))
    except OSError:
        return False


def _test_has_auth_coverage(test_file: Optional[Path]) -> bool:
    if test_file is None:
        return False
    try:
        return bool(_AUTH_PATTERNS.search(test_file.read_text(encoding="utf-8", errors="replace")))
    except OSError:
        return False


def _test_has_edge_cases(test_file: Optional[Path]) -> bool:
    if test_file is None:
        return False
    try:
        return bool(_EDGE_PATTERNS.search(test_file.read_text(encoding="utf-8", errors="replace")))
    except OSError:
        return False


def _test_has_regression(test_file: Optional[Path]) -> bool:
    if test_file is None:
        return False
    try:
        return bool(_REGRESSION_PATTERNS.search(test_file.read_text(encoding="utf-8", errors="replace")))
    except OSError:
        return False


# ------------------------------------------------------------------ #
# TestPilot                                                            #
# ------------------------------------------------------------------ #


class TestPilot:
    """
    PRISM Testing Reviewer.

    Usage::

        pilot = TestPilot(root="path/to/repo")
        result = pilot.review()

    The *source_dirs* and *test_dirs* parameters can be used to restrict
    which directories are scanned.  Both default to sensible conventions.
    """

    def __init__(
        self,
        root: str | Path = ".",
        source_dirs: Optional[list[str]] = None,
        test_dirs: Optional[list[str]] = None,
    ) -> None:
        self.root = Path(root).resolve()
        self._source_dirs = source_dirs or ["src", "app", "lib", "prism", "."]
        self._test_dirs = test_dirs or ["tests", "test"]
        self._finding_counter = 0

    # ---------------------------------------------------------------- #
    # Public API                                                         #
    # ---------------------------------------------------------------- #

    def review(self) -> ReviewResult:
        """Run all test-quality checks and return a ReviewResult."""
        result = ReviewResult(reviewer="TestPilot")
        source_files = self._collect_source_files()
        test_dirs = self._resolve_test_dirs()

        for src in source_files:
            test_file = _find_test_file(src, test_dirs)
            rel = src.relative_to(self.root)

            # 1. Entirely missing test file
            if test_file is None:
                result.findings.append(self._missing_test_file(rel))
                continue

            # 2. No assertions
            if not _has_assertions(test_file):
                result.findings.append(self._no_assertions(rel, test_file))

            # 3. Untested public functions
            public_fns = _collect_public_functions(src)
            test_names = _collect_test_function_names(test_file)
            for fn_name, lineno in public_fns:
                if not any(fn_name.lower() in t.lower() for t in test_names):
                    result.findings.append(
                        self._untested_function(rel, fn_name, lineno)
                    )

            # 4. Missing edge-case tests
            if not _test_has_edge_cases(test_file):
                result.findings.append(self._missing_edge_cases(rel, test_file))

            # 5. Auth logic without auth tests
            if _source_has_auth(src) and not _test_has_auth_coverage(test_file):
                result.findings.append(self._missing_auth_tests(rel, test_file))

            # 6. Missing regression tests (advisory)
            if not _test_has_regression(test_file):
                result.findings.append(self._missing_regression(rel, test_file))

        result.metadata = {
            "source_files_scanned": len(source_files),
            "test_dirs": [str(d) for d in test_dirs],
        }
        return result

    # ---------------------------------------------------------------- #
    # Finding factories                                                  #
    # ---------------------------------------------------------------- #

    def _next_id(self) -> str:
        self._finding_counter += 1
        return f"TEST-{self._finding_counter:03d}"

    def _missing_test_file(self, source: Path) -> Finding:
        return Finding(
            id=self._next_id(),
            category=Category.TESTING,
            severity=Severity.HIGH,
            title=f"No test file for {source.name}",
            description=(
                f"No corresponding test file was found for '{source}'. "
                "All source modules should have a dedicated test file."
            ),
            file=str(source),
            evidence=f"Searched for test_{source.stem}.py / {source.stem}_test.py in test directories.",
            suggested_fix=f"Create tests/test_{source.stem}.py and add unit tests.",
            fix_recommendation="Add a test file with at least happy-path and error-path tests.",
            requires_human_approval=False,
            status=FindingStatus.OPEN,
        )

    def _no_assertions(self, source: Path, test_file: Path) -> Finding:
        rel_test = test_file.relative_to(self.root) if test_file.is_absolute() else test_file
        return Finding(
            id=self._next_id(),
            category=Category.TESTING,
            severity=Severity.HIGH,
            title=f"Test file for {source.name} contains no assertions",
            description=(
                f"'{rel_test}' does not contain any assert statements or assertion calls. "
                "Tests without assertions do not validate behaviour."
            ),
            file=str(rel_test),
            evidence="No 'assert', assertX(), or expect() calls found.",
            suggested_fix="Add assertions that verify expected output and side-effects.",
            fix_recommendation="Use pytest assert statements or unittest assertX methods.",
            requires_human_approval=False,
            status=FindingStatus.OPEN,
        )

    def _untested_function(self, source: Path, fn_name: str, lineno: int) -> Finding:
        return Finding(
            id=self._next_id(),
            category=Category.TESTING,
            severity=Severity.MEDIUM,
            title=f"Function '{fn_name}' in {source.name} has no test",
            description=(
                f"Public function '{fn_name}' (line {lineno}) in '{source}' "
                "has no corresponding test function."
            ),
            file=str(source),
            line=lineno,
            evidence=f"No test function name containing '{fn_name}' found in test file.",
            suggested_fix=f"Add a test function named 'test_{fn_name}' covering the main behaviour.",
            fix_recommendation="Cover happy path, invalid inputs, and boundary values.",
            requires_human_approval=False,
            status=FindingStatus.OPEN,
        )

    def _missing_edge_cases(self, source: Path, test_file: Path) -> Finding:
        rel_test = test_file.relative_to(self.root) if test_file.is_absolute() else test_file
        return Finding(
            id=self._next_id(),
            category=Category.TESTING,
            severity=Severity.MEDIUM,
            title=f"No edge-case tests detected for {source.name}",
            description=(
                f"'{rel_test}' does not appear to contain edge-case or error-path tests. "
                "Tests should cover empty inputs, None values, boundary values, and exceptions."
            ),
            file=str(rel_test),
            evidence="No test names or comments containing: invalid, empty, none, boundary, error, exception, raises.",
            suggested_fix="Add tests that cover invalid input, empty collections, None arguments, and raised exceptions.",
            fix_recommendation="Use pytest.raises() for exception paths and parametrize for boundary values.",
            requires_human_approval=False,
            status=FindingStatus.OPEN,
        )

    def _missing_auth_tests(self, source: Path, test_file: Path) -> Finding:
        rel_test = test_file.relative_to(self.root) if test_file.is_absolute() else test_file
        return Finding(
            id=self._next_id(),
            category=Category.TESTING,
            severity=Severity.HIGH,
            title=f"Authentication logic in {source.name} lacks auth tests",
            description=(
                f"'{source}' contains authentication/authorisation logic but "
                f"'{rel_test}' does not appear to test it. "
                "Missing auth tests can leave security vulnerabilities undetected."
            ),
            file=str(rel_test),
            evidence=f"Auth-related identifiers found in {source.name}; none found in test file.",
            suggested_fix=(
                "Add tests for: successful authentication, failed authentication, "
                "invalid token/credentials, expired token, and unauthorised access."
            ),
            fix_recommendation="Cover both success and failure paths for every auth-related function.",
            requires_human_approval=True,
            status=FindingStatus.OPEN,
        )

    def _missing_regression(self, source: Path, test_file: Path) -> Finding:
        rel_test = test_file.relative_to(self.root) if test_file.is_absolute() else test_file
        return Finding(
            id=self._next_id(),
            category=Category.TESTING,
            severity=Severity.LOW,
            title=f"No regression tests found for {source.name}",
            description=(
                f"'{rel_test}' does not appear to contain regression tests. "
                "Regression tests guard against previously fixed bugs resurfacing."
            ),
            file=str(rel_test),
            evidence="No comments or function names referencing: regression, bug, fix, issue, ticket.",
            suggested_fix="Add regression tests with comments linking to issue tracker references.",
            fix_recommendation="Add a comment like '# Regression: GH-42' above the relevant test.",
            requires_human_approval=False,
            status=FindingStatus.OPEN,
        )

    # ---------------------------------------------------------------- #
    # Internal helpers                                                   #
    # ---------------------------------------------------------------- #

    def _resolve_test_dirs(self) -> list[Path]:
        dirs = []
        for d in self._test_dirs:
            p = self.root / d
            if p.is_dir():
                dirs.append(p)
        return dirs

    def _collect_source_files(self) -> list[Path]:
        """Collect all non-test Python source files under source_dirs."""
        files: list[Path] = []
        seen: set[Path] = set()
        for d in self._source_dirs:
            search_root = self.root / d
            if not search_root.is_dir():
                # Fall back: if "." treat workspace root directly
                if d == ".":
                    search_root = self.root
                else:
                    continue
            for path in sorted(search_root.rglob("*.py")):
                resolved = path.resolve()
                if resolved in seen:
                    continue
                seen.add(resolved)
                if _is_test_file(path):
                    continue
                if path.name == "__init__.py":
                    continue
                # Skip anything inside a test directory
                parts = path.parts
                if any(p in ("tests", "test") for p in parts):
                    continue
                files.append(path)
        return files
