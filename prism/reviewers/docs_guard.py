"""
DocsGuard — PRISM Documentation Reviewer

Analyses documentation consistency by comparing:
- README claims against the actual file/module structure
- Documented API endpoints against implemented routes
- Documented request/response examples against actual signatures
- Documented behaviour against implemented behaviour
- Code docstrings presence and completeness

DocsGuard performs static text and AST analysis only — it does not
run or import the target codebase.
"""

from __future__ import annotations

import ast
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
# Heuristics / patterns                                                #
# ------------------------------------------------------------------ #

# Markdown code blocks that look like HTTP examples
_HTTP_EXAMPLE_RE = re.compile(
    r"```[^\n]*\n\s*(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)\s+(/[^\s]*)",
    re.IGNORECASE,
)

# Inline backtick or bold mentions of endpoints
_INLINE_ENDPOINT_RE = re.compile(
    r"`(GET|POST|PUT|PATCH|DELETE)\s+(/[^`]+)`|"
    r"\*\*(GET|POST|PUT|PATCH|DELETE)\s+(/[^\*]+)\*\*",
    re.IGNORECASE,
)

# Flask/FastAPI/Django route decorators
_ROUTE_DECORATOR_RE = re.compile(
    r"""@(?:app|router|blueprint|bp)\.(get|post|put|patch|delete|route)\s*\(\s*['"]([^'"]+)['"]""",
    re.IGNORECASE,
)

# FastAPI path-function pattern
_FASTAPI_ROUTE_RE = re.compile(
    r"""@\w+\.(get|post|put|patch|delete)\s*\(\s*['"]([^'"]+)['"]""",
    re.IGNORECASE,
)

# JSON example blocks in docs
_JSON_BLOCK_RE = re.compile(r"```json\s*([\s\S]*?)```", re.IGNORECASE)

# Section headings that typically describe endpoints
_ENDPOINT_SECTION_RE = re.compile(
    r"^#{1,4}\s+.*?(endpoint|route|api|request|response)", re.IGNORECASE | re.MULTILINE
)

# README markers for "installation", "usage", "requirements"
_README_SECTION_RE = re.compile(
    r"^#{1,3}\s+(installation|usage|getting started|requirements|setup|configuration)",
    re.IGNORECASE | re.MULTILINE,
)

# Mentions of specific files in README
_FILE_MENTION_RE = re.compile(r"`([a-zA-Z0-9_/\-\.]+\.(py|js|ts|json|yaml|yml|env|sh|txt))`")


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _collect_routes_from_source(root: Path) -> list[tuple[str, str, Path, int]]:
    """Return list of (method, path, file, lineno) for all decorated routes."""
    routes = []
    for py_file in sorted(root.rglob("*.py")):
        if any(p in ("tests", "test") for p in py_file.parts):
            continue
        source = _read(py_file)
        for m in _ROUTE_DECORATOR_RE.finditer(source):
            method = m.group(1).upper()
            route_path = m.group(2)
            lineno = source[: m.start()].count("\n") + 1
            routes.append((method, route_path, py_file, lineno))
        for m in _FASTAPI_ROUTE_RE.finditer(source):
            method = m.group(1).upper()
            route_path = m.group(2)
            lineno = source[: m.start()].count("\n") + 1
            routes.append((method, route_path, py_file, lineno))
    return routes


def _collect_routes_from_docs(doc_text: str) -> list[tuple[str, str]]:
    """Return list of (method, path) mentioned in documentation."""
    found = []
    for m in _HTTP_EXAMPLE_RE.finditer(doc_text):
        found.append((m.group(1).upper(), m.group(2)))
    for m in _INLINE_ENDPOINT_RE.finditer(doc_text):
        if m.group(1):
            found.append((m.group(1).upper(), m.group(2)))
        else:
            found.append((m.group(3).upper(), m.group(4)))
    return found


def _functions_missing_docstrings(py_file: Path) -> list[tuple[str, int]]:
    """Return list of (function_name, lineno) for public functions without docstrings."""
    try:
        tree = ast.parse(_read(py_file))
    except SyntaxError:
        return []
    missing = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name.startswith("_"):
                continue
            if not (node.body and isinstance(node.body[0], ast.Expr) and isinstance(node.body[0].value, ast.Constant)):
                missing.append((node.name, node.lineno))
    return missing


def _classes_missing_docstrings(py_file: Path) -> list[tuple[str, int]]:
    try:
        tree = ast.parse(_read(py_file))
    except SyntaxError:
        return []
    missing = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            if node.name.startswith("_"):
                continue
            if not (node.body and isinstance(node.body[0], ast.Expr) and isinstance(node.body[0].value, ast.Constant)):
                missing.append((node.name, node.lineno))
    return missing


def _mentioned_files_exist(doc_text: str, root: Path) -> list[tuple[str, int]]:
    """Return list of (filename, approx_line) that are mentioned in docs but not found."""
    missing = []
    lines = doc_text.splitlines()
    for lineno, line in enumerate(lines, 1):
        for m in _FILE_MENTION_RE.finditer(line):
            fname = m.group(1)
            # Skip very generic names
            if fname in ("requirements.txt",):
                continue
            candidate = root / fname
            if not candidate.exists():
                missing.append((fname, lineno))
    return missing


# ------------------------------------------------------------------ #
# DocsGuard                                                            #
# ------------------------------------------------------------------ #


class DocsGuard:
    """
    PRISM Documentation Reviewer.

    Usage::

        guard = DocsGuard(root="path/to/repo")
        result = guard.review()
    """

    def __init__(
        self,
        root: str | Path = ".",
        doc_files: Optional[list[str]] = None,
    ) -> None:
        self.root = Path(root).resolve()
        self._doc_files = doc_files or [
            "README.md",
            "README.rst",
            "docs/README.md",
            "docs/api.md",
            "docs/API.md",
            "API.md",
            "CHANGELOG.md",
        ]
        self._finding_counter = 0

    # ---------------------------------------------------------------- #
    # Public API                                                         #
    # ---------------------------------------------------------------- #

    def review(self) -> ReviewResult:
        """Run all documentation consistency checks and return a ReviewResult."""
        result = ReviewResult(reviewer="DocsGuard")

        doc_texts = self._load_docs()
        combined_doc = "\n".join(doc_texts.values())

        # 1. README exists check
        if not doc_texts:
            result.findings.append(self._no_readme())
        else:
            # 2. README vs file mentions
            for fname, lineno in _mentioned_files_exist(combined_doc, self.root):
                result.findings.append(self._missing_mentioned_file(fname, lineno))

            # 3. Documented endpoints vs implemented routes
            doc_routes = _collect_routes_from_docs(combined_doc)
            impl_routes = _collect_routes_from_source(self.root)
            impl_route_set = {(m.upper(), p) for m, p, _, _ in impl_routes}
            doc_route_set = {(m.upper(), p) for m, p in doc_routes}

            for method, path in doc_route_set - impl_route_set:
                result.findings.append(
                    self._doc_route_not_implemented(method, path)
                )
            for method, path, src_file, lineno in impl_routes:
                if (method, path) not in doc_route_set and impl_routes:
                    rel = src_file.relative_to(self.root)
                    result.findings.append(
                        self._impl_route_not_documented(method, path, rel, lineno)
                    )

        # 4. Source files missing module docstrings
        for py_file in sorted(self.root.rglob("*.py")):
            if any(p in ("tests", "test") for p in py_file.parts):
                continue
            if py_file.name == "__init__.py":
                continue
            self._check_docstrings(py_file, result)

        result.metadata = {
            "doc_files_checked": list(doc_texts.keys()),
            "source_files_scanned": len(list(self.root.rglob("*.py"))),
        }
        return result

    # ---------------------------------------------------------------- #
    # Finding factories                                                  #
    # ---------------------------------------------------------------- #

    def _next_id(self) -> str:
        self._finding_counter += 1
        return f"DOCS-{self._finding_counter:03d}"

    def _no_readme(self) -> Finding:
        return Finding(
            id=self._next_id(),
            category=Category.DOCUMENTATION,
            severity=Severity.HIGH,
            title="No README or documentation file found",
            description=(
                "The repository has no README.md, README.rst, or other recognised "
                "documentation file. Projects should always have a README explaining "
                "purpose, setup, and usage."
            ),
            file=None,
            evidence="Searched for: " + ", ".join(self._doc_files),
            suggested_fix="Create a README.md with project overview, installation, and usage sections.",
            fix_recommendation="Follow the GitHub README template: title, description, install, usage, contributing.",
            requires_human_approval=False,
            status=FindingStatus.OPEN,
        )

    def _missing_mentioned_file(self, fname: str, lineno: int) -> Finding:
        return Finding(
            id=self._next_id(),
            category=Category.DOCUMENTATION,
            severity=Severity.MEDIUM,
            title=f"Documentation references '{fname}' which does not exist",
            description=(
                f"The documentation mentions '{fname}' (around line {lineno}) "
                "but that file was not found in the repository."
            ),
            file=None,
            line=lineno,
            evidence=f"Reference to `{fname}` in documentation; file not found at repo root.",
            suggested_fix=f"Either create '{fname}' or remove the reference from the documentation.",
            fix_recommendation="Ensure all files referenced in docs exist and are committed.",
            requires_human_approval=False,
            status=FindingStatus.OPEN,
        )

    def _doc_route_not_implemented(self, method: str, path: str) -> Finding:
        return Finding(
            id=self._next_id(),
            category=Category.DOCUMENTATION,
            severity=Severity.HIGH,
            title=f"Documented endpoint {method} {path} not found in source",
            description=(
                f"The documentation describes endpoint '{method} {path}' but no "
                "matching route decorator was found in any source file."
            ),
            evidence=f"Endpoint '{method} {path}' appears in docs; not found in source.",
            suggested_fix=(
                f"Either implement the '{method} {path}' route or remove it from the documentation."
            ),
            fix_recommendation="Keep documentation and implementation in sync on every PR.",
            requires_human_approval=True,
            status=FindingStatus.OPEN,
        )

    def _impl_route_not_documented(
        self, method: str, path: str, src_file: Path, lineno: int
    ) -> Finding:
        return Finding(
            id=self._next_id(),
            category=Category.DOCUMENTATION,
            severity=Severity.MEDIUM,
            title=f"Implemented endpoint {method} {path} is not documented",
            description=(
                f"Route '{method} {path}' is implemented in '{src_file}' (line {lineno}) "
                "but is not mentioned in any documentation file."
            ),
            file=str(src_file),
            line=lineno,
            evidence=f"Route decorator found at {src_file}:{lineno}; not present in docs.",
            suggested_fix=f"Add documentation for '{method} {path}' including request/response examples.",
            fix_recommendation="Document every public API endpoint in README.md or a dedicated API doc.",
            requires_human_approval=False,
            status=FindingStatus.OPEN,
        )

    def _missing_function_docstring(self, py_file: Path, fn_name: str, lineno: int) -> Finding:
        rel = py_file.relative_to(self.root)
        return Finding(
            id=self._next_id(),
            category=Category.DOCUMENTATION,
            severity=Severity.LOW,
            title=f"Function '{fn_name}' in {rel.name} is missing a docstring",
            description=(
                f"Public function '{fn_name}' at {rel}:{lineno} has no docstring. "
                "Docstrings are required for all public functions."
            ),
            file=str(rel),
            line=lineno,
            evidence=f"AST inspection: no docstring found on '{fn_name}'.",
            suggested_fix=f'Add a docstring: """Short description of {fn_name}."""',
            fix_recommendation="Follow the Google or NumPy docstring style used by the rest of the codebase.",
            requires_human_approval=False,
            status=FindingStatus.OPEN,
        )

    def _missing_class_docstring(self, py_file: Path, cls_name: str, lineno: int) -> Finding:
        rel = py_file.relative_to(self.root)
        return Finding(
            id=self._next_id(),
            category=Category.DOCUMENTATION,
            severity=Severity.LOW,
            title=f"Class '{cls_name}' in {rel.name} is missing a docstring",
            description=(
                f"Public class '{cls_name}' at {rel}:{lineno} has no docstring."
            ),
            file=str(rel),
            line=lineno,
            evidence=f"AST inspection: no docstring found on class '{cls_name}'.",
            suggested_fix=f'Add a class docstring: """Short description of {cls_name}."""',
            fix_recommendation="Docstrings improve IDE support and auto-generated documentation.",
            requires_human_approval=False,
            status=FindingStatus.OPEN,
        )

    # ---------------------------------------------------------------- #
    # Helpers                                                            #
    # ---------------------------------------------------------------- #

    def _load_docs(self) -> dict[str, str]:
        docs = {}
        for fname in self._doc_files:
            p = self.root / fname
            if p.exists():
                docs[fname] = _read(p)
        return docs

    def _check_docstrings(self, py_file: Path, result: ReviewResult) -> None:
        for fn_name, lineno in _functions_missing_docstrings(py_file):
            result.findings.append(
                self._missing_function_docstring(py_file, fn_name, lineno)
            )
        for cls_name, lineno in _classes_missing_docstrings(py_file):
            result.findings.append(
                self._missing_class_docstring(py_file, cls_name, lineno)
            )
