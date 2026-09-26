"""
DocAgent — Documentation Reviewer
====================================
Analyses documentation consistency and code docstring coverage.

Checks performed:
  D-01  No README or documentation file found
  D-02  Documentation references a file that does not exist
  D-03  Documented API endpoint not found in source
  D-04  Implemented route not mentioned in documentation
  D-05  Public function missing a docstring
  D-06  Public class missing a docstring

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

_HTTP_EXAMPLE_RE = re.compile(
    r"```[^\n]*\n\s*(GET|POST|PUT|PATCH|DELETE)\s+(/[^\s]*)",
    re.IGNORECASE,
)
_INLINE_ENDPOINT_RE = re.compile(
    r"`(GET|POST|PUT|PATCH|DELETE)\s+(/[^`]+)`",
    re.IGNORECASE,
)
_ROUTE_DECORATOR_RE = re.compile(
    r"""@(?:app|router|blueprint|bp)\.(get|post|put|patch|delete|route)\s*\(\s*['"]([^'"]+)['"]""",
    re.IGNORECASE,
)
_FILE_MENTION_RE = re.compile(
    r"`([a-zA-Z0-9_/\-\.]+\.(py|js|ts|json|yaml|yml|sh|txt))`"
)
_DOC_FILES = ["README.md", "docs/README.md", "docs/api.md", "CHANGELOG.md"]


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _collect_doc_routes(text: str) -> list[tuple[str, str]]:
    found = []
    for m in _HTTP_EXAMPLE_RE.finditer(text):
        found.append((m.group(1).upper(), m.group(2)))
    for m in _INLINE_ENDPOINT_RE.finditer(text):
        found.append((m.group(1).upper(), m.group(2)))
    return found


def _collect_impl_routes(root: Path) -> list[tuple[str, str, str, int]]:
    routes = []
    for py_file in sorted(root.rglob("*.py")):
        src = _read(py_file)
        for m in _ROUTE_DECORATOR_RE.finditer(src):
            method = m.group(1).upper()
            path = m.group(2)
            lineno = src[: m.start()].count("\n") + 1
            routes.append((method, path, str(py_file.relative_to(root)), lineno))
    return routes


def _functions_missing_docstrings(py_file: Path) -> list[tuple[str, int]]:
    try:
        tree = ast.parse(_read(py_file))
    except SyntaxError:
        return []
    missing = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name.startswith("_"):
                continue
            if not (node.body and isinstance(node.body[0], ast.Expr)
                    and isinstance(node.body[0].value, ast.Constant)):
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
            if not (node.body and isinstance(node.body[0], ast.Expr)
                    and isinstance(node.body[0].value, ast.Constant)):
                missing.append((node.name, node.lineno))
    return missing


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def scan_directory(directory: Path) -> list[Finding]:
    """Run all documentation checks across the repository."""
    root = directory
    findings: list[Finding] = []

    # Load docs
    doc_texts = {}
    for fname in _DOC_FILES:
        p = root / fname
        if p.exists():
            doc_texts[fname] = _read(p)
    combined = "\n".join(doc_texts.values())

    # D-01 — no README
    if not doc_texts:
        findings.append(Finding(
            agent="DocAgent", rule_id="D-01", severity="HIGH",
            file=".", line=1,
            message="No README or documentation file found",
            snippet="",
            fix_hint="Create a README.md with project overview, installation, and usage.",
        ))
    else:
        # D-02 — broken file references
        for lineno, line in enumerate(combined.splitlines(), 1):
            for m in _FILE_MENTION_RE.finditer(line):
                fname = m.group(1)
                if fname in ("requirements.txt",):
                    continue
                if not (root / fname).exists():
                    findings.append(Finding(
                        agent="DocAgent", rule_id="D-02", severity="MEDIUM",
                        file="README.md", line=lineno,
                        message=f"Documentation references '{fname}' which does not exist",
                        snippet=fname,
                        fix_hint=f"Create '{fname}' or remove the reference from docs.",
                    ))

        # D-03 / D-04 — route documentation vs implementation
        doc_routes = set(_collect_doc_routes(combined))
        impl_routes = _collect_impl_routes(root)
        impl_route_set = {(m, p) for m, p, _, _ in impl_routes}

        for method, path in doc_routes - impl_route_set:
            findings.append(Finding(
                agent="DocAgent", rule_id="D-03", severity="HIGH",
                file="README.md", line=1,
                message=f"Documented endpoint {method} {path} not found in source",
                snippet=f"{method} {path}",
                fix_hint=f"Implement '{method} {path}' or remove it from the docs.",
            ))
        for method, path, src_file, lineno in impl_routes:
            if (method, path) not in doc_routes:
                findings.append(Finding(
                    agent="DocAgent", rule_id="D-04", severity="MEDIUM",
                    file=src_file, line=lineno,
                    message=f"Implemented endpoint {method} {path} is not documented",
                    snippet=f"{method} {path}",
                    fix_hint=f"Add documentation for '{method} {path}' in README.md.",
                ))

    # D-05 / D-06 — missing docstrings
    for py_file in sorted(root.rglob("*.py")):
        if any(p in ("tests", "test") for p in py_file.parts):
            continue
        if py_file.name == "__init__.py":
            continue
        rel = str(py_file.relative_to(root))
        for fn_name, lineno in _functions_missing_docstrings(py_file):
            findings.append(Finding(
                agent="DocAgent", rule_id="D-05", severity="LOW",
                file=rel, line=lineno,
                message=f"Function '{fn_name}' is missing a docstring",
                snippet=fn_name,
                fix_hint=f'Add: """{fn_name} — short description."""',
            ))
        for cls_name, lineno in _classes_missing_docstrings(py_file):
            findings.append(Finding(
                agent="DocAgent", rule_id="D-06", severity="LOW",
                file=rel, line=lineno,
                message=f"Class '{cls_name}' is missing a docstring",
                snippet=cls_name,
                fix_hint=f'Add: """{cls_name} — short description."""',
            ))

    return findings
