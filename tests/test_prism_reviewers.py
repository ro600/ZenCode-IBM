"""
tests/test_prism_reviewers.py
==============================
Tests for Person 2 (Aaryan) components:

  - prism/models.py          — Finding, ReviewResult serialisation, status helpers
  - prism/reviewers/test_pilot.py  — TestPilot finding generation
  - prism/reviewers/docs_guard.py  — DocsGuard finding generation
  - prism/dashboard/aggregator.py  — Aggregator, DashboardState, final_results
  - Approve / reject / fix controls
  - Final result calculations

All tests are self-contained (tmp_path fixtures) and do NOT require
SQLAlchemy, FastAPI, or the Flask app to be running.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from prism.models import (
    Category,
    Finding,
    FindingStatus,
    ReviewResult,
    Severity,
)
from prism.reviewers.test_pilot import TestPilot
from prism.reviewers.docs_guard import DocsGuard
from prism.dashboard.aggregator import Aggregator, DashboardState, PRMetadata


# ================================================================
# Helpers
# ================================================================

def _make_finding(
    fid: str = "TEST-001",
    category: Category = Category.TESTING,
    severity: Severity = Severity.MEDIUM,
    status: FindingStatus = FindingStatus.OPEN,
    requires_human_approval: bool = False,
    title: str = "A test finding",
) -> Finding:
    return Finding(
        id=fid,
        category=category,
        severity=severity,
        title=title,
        description="Test description.",
        file="app/main.py",
        line=10,
        evidence="evidence text",
        suggested_fix="Fix it.",
        fix_recommendation="Broader guidance.",
        requires_human_approval=requires_human_approval,
        status=status,
    )


# ================================================================
# Finding — serialisation
# ================================================================

class TestFindingSerialization:
    def test_to_dict_has_required_keys(self):
        f = _make_finding()
        d = f.to_dict()
        for key in ("id", "category", "severity", "title", "description",
                    "file", "line", "evidence", "suggested_fix",
                    "fix_recommendation", "requires_human_approval", "status"):
            assert key in d, f"Missing key: {key}"

    def test_to_dict_enum_values_are_strings(self):
        f = _make_finding(category=Category.SECURITY, severity=Severity.CRITICAL)
        d = f.to_dict()
        assert d["category"] == "security"
        assert d["severity"] == "critical"
        assert d["status"] == "open"

    def test_to_json_is_valid_json(self):
        f = _make_finding()
        parsed = json.loads(f.to_json())
        assert parsed["id"] == "TEST-001"

    def test_from_dict_round_trip(self):
        original = _make_finding(
            fid="DOCS-007",
            category=Category.DOCUMENTATION,
            severity=Severity.LOW,
        )
        reconstructed = Finding.from_dict(original.to_dict())
        assert reconstructed.id == original.id
        assert reconstructed.category == original.category
        assert reconstructed.severity == original.severity
        assert reconstructed.status == original.status

    def test_from_dict_defaults_status_to_open(self):
        data = {
            "id": "X-001",
            "category": "bug",
            "severity": "high",
            "title": "t",
            "description": "d",
        }
        f = Finding.from_dict(data)
        assert f.status == FindingStatus.OPEN
        assert f.requires_human_approval is False


# ================================================================
# Finding — status helpers
# ================================================================

class TestFindingStatusHelpers:
    def test_approve_sets_approved(self):
        f = _make_finding()
        f.approve()
        assert f.status == FindingStatus.APPROVED

    def test_reject_sets_rejected(self):
        f = _make_finding()
        f.reject()
        assert f.status == FindingStatus.REJECTED

    def test_mark_fixed_sets_fixed(self):
        f = _make_finding()
        f.mark_fixed()
        assert f.status == FindingStatus.FIXED

    def test_flag_for_review_sets_pending_and_human_flag(self):
        f = _make_finding(requires_human_approval=False)
        f.flag_for_review()
        assert f.status == FindingStatus.PENDING_REVIEW
        assert f.requires_human_approval is True

    def test_approve_then_fix(self):
        f = _make_finding()
        f.approve()
        f.mark_fixed()
        assert f.status == FindingStatus.FIXED


# ================================================================
# ReviewResult
# ================================================================

class TestReviewResult:
    def test_finding_count_property(self):
        result = ReviewResult(reviewer="TestPilot")
        assert result.finding_count == 0
        result.findings.append(_make_finding())
        assert result.finding_count == 1

    def test_findings_by_severity(self):
        result = ReviewResult(reviewer="TestPilot")
        result.findings.append(_make_finding(severity=Severity.HIGH))
        result.findings.append(_make_finding(fid="T-002", severity=Severity.LOW))
        highs = result.findings_by_severity(Severity.HIGH)
        assert len(highs) == 1
        assert highs[0].id == "TEST-001"

    def test_findings_by_category(self):
        result = ReviewResult(reviewer="DocsGuard")
        result.findings.append(_make_finding(category=Category.TESTING))
        result.findings.append(_make_finding(fid="D-002", category=Category.DOCUMENTATION))
        docs = result.findings_by_category(Category.DOCUMENTATION)
        assert len(docs) == 1

    def test_to_dict_structure(self):
        result = ReviewResult(reviewer="TestPilot")
        result.findings.append(_make_finding())
        d = result.to_dict()
        assert d["reviewer"] == "TestPilot"
        assert isinstance(d["findings"], list)
        assert len(d["findings"]) == 1


# ================================================================
# TestPilot — finding generation
# ================================================================

class TestTestPilotFindings:

    def test_detects_missing_test_file(self, tmp_path):
        """A source file with no corresponding test file produces a HIGH finding."""
        src = tmp_path / "app"
        src.mkdir()
        (src / "service.py").write_text("def do_work(): pass\n")

        pilot = TestPilot(root=tmp_path, source_dirs=["app"], test_dirs=["tests"])
        result = pilot.review()

        missing = [f for f in result.findings if "No test file" in f.title]
        assert len(missing) >= 1
        assert all(f.severity == Severity.HIGH for f in missing)
        assert all(f.category == Category.TESTING for f in missing)

    def test_detects_no_assertions(self, tmp_path):
        """A test file with no assert statements is flagged as HIGH."""
        src = tmp_path / "app"
        src.mkdir()
        (src / "utils.py").write_text("def add(a, b): return a + b\n")

        test_dir = tmp_path / "tests"
        test_dir.mkdir()
        (test_dir / "test_utils.py").write_text(
            "def test_add():\n    add(1, 2)  # no assertion\n"
        )

        pilot = TestPilot(root=tmp_path, source_dirs=["app"], test_dirs=["tests"])
        result = pilot.review()

        no_assert = [f for f in result.findings if "no assertions" in f.title.lower()]
        assert len(no_assert) >= 1
        assert no_assert[0].severity == Severity.HIGH

    def test_detects_untested_public_function(self, tmp_path):
        """Public function with no matching test function is flagged as MEDIUM."""
        src = tmp_path / "app"
        src.mkdir()
        (src / "calc.py").write_text(
            "def multiply(a, b):\n    return a * b\n"
            "def divide(a, b):\n    return a / b\n"
        )

        test_dir = tmp_path / "tests"
        test_dir.mkdir()
        (test_dir / "test_calc.py").write_text(
            "def test_multiply():\n    assert True\n"
        )

        pilot = TestPilot(root=tmp_path, source_dirs=["app"], test_dirs=["tests"])
        result = pilot.review()

        untested = [f for f in result.findings if "divide" in f.title]
        assert len(untested) >= 1
        assert untested[0].severity == Severity.MEDIUM

    def test_detects_missing_auth_tests(self, tmp_path):
        """Source with auth keywords but test file without them is flagged HIGH."""
        src = tmp_path / "app"
        src.mkdir()
        (src / "auth.py").write_text(
            "def authenticate(username, password):\n    return verify_token(password)\n"
        )

        test_dir = tmp_path / "tests"
        test_dir.mkdir()
        (test_dir / "test_auth.py").write_text(
            "def test_something():\n    assert 1 == 1\n"
        )

        pilot = TestPilot(root=tmp_path, source_dirs=["app"], test_dirs=["tests"])
        result = pilot.review()

        auth_findings = [f for f in result.findings if "lacks auth tests" in f.title.lower()]
        assert len(auth_findings) >= 1
        assert auth_findings[0].severity == Severity.HIGH
        assert auth_findings[0].requires_human_approval is True

    def test_detects_missing_edge_cases(self, tmp_path):
        """Test file with no edge-case vocabulary produces a MEDIUM finding."""
        src = tmp_path / "app"
        src.mkdir()
        (src / "parser.py").write_text("def parse(data): return data\n")

        test_dir = tmp_path / "tests"
        test_dir.mkdir()
        (test_dir / "test_parser.py").write_text(
            "def test_parse():\n    assert parse('x') == 'x'\n"
        )

        pilot = TestPilot(root=tmp_path, source_dirs=["app"], test_dirs=["tests"])
        result = pilot.review()

        edge = [f for f in result.findings if "edge" in f.title.lower()]
        assert len(edge) >= 1
        assert edge[0].severity == Severity.MEDIUM

    def test_detects_missing_regression_tests(self, tmp_path):
        """No regression keywords in test file produces a LOW advisory."""
        src = tmp_path / "app"
        src.mkdir()
        (src / "widget.py").write_text("def render(): return '<div/>'\n")

        test_dir = tmp_path / "tests"
        test_dir.mkdir()
        (test_dir / "test_widget.py").write_text(
            "def test_render():\n    assert render() == '<div/>'\n"
        )

        pilot = TestPilot(root=tmp_path, source_dirs=["app"], test_dirs=["tests"])
        result = pilot.review()

        regression = [f for f in result.findings if "regression" in f.title.lower()]
        assert len(regression) >= 1
        assert regression[0].severity == Severity.LOW

    def test_no_missing_test_file_when_test_exists(self, tmp_path):
        """If a proper test file with assertions exists, no T-01 finding."""
        src = tmp_path / "app"
        src.mkdir()
        (src / "helper.py").write_text("def greet(name): return f'Hi {name}'\n")

        test_dir = tmp_path / "tests"
        test_dir.mkdir()
        (test_dir / "test_helper.py").write_text(
            "def test_greet():\n    assert greet('world') == 'Hi world'\n"
        )

        pilot = TestPilot(root=tmp_path, source_dirs=["app"], test_dirs=["tests"])
        result = pilot.review()

        missing = [f for f in result.findings if "No test file" in f.title]
        assert len(missing) == 0

    def test_result_has_metadata(self, tmp_path):
        """The ReviewResult includes metadata about the scan."""
        (tmp_path / "app").mkdir()
        pilot = TestPilot(root=tmp_path, source_dirs=["app"], test_dirs=["tests"])
        result = pilot.review()
        assert "source_files_scanned" in result.metadata
        assert "test_dirs" in result.metadata

    def test_finding_ids_are_sequential(self, tmp_path):
        """Finding IDs use the TEST-NNN format and are sequential."""
        src = tmp_path / "src"
        src.mkdir()
        (src / "a.py").write_text("def foo(): pass\n")
        (src / "b.py").write_text("def bar(): pass\n")

        pilot = TestPilot(root=tmp_path, source_dirs=["src"], test_dirs=["tests"])
        result = pilot.review()
        ids = [f.id for f in result.findings]
        assert all(fid.startswith("TEST-") for fid in ids)
        # IDs should be unique
        assert len(set(ids)) == len(ids)

    def test_reviewer_name_is_testpilot(self, tmp_path):
        pilot = TestPilot(root=tmp_path)
        result = pilot.review()
        assert result.reviewer == "TestPilot"


# ================================================================
# DocsGuard — finding generation
# ================================================================

class TestDocsGuardFindings:

    def test_detects_no_readme(self, tmp_path):
        """No docs at all produces a HIGH finding."""
        guard = DocsGuard(root=tmp_path, doc_files=["README.md"])
        result = guard.review()

        no_readme = [f for f in result.findings if "No README" in f.title]
        assert len(no_readme) >= 1
        assert no_readme[0].severity == Severity.HIGH
        assert no_readme[0].category == Category.DOCUMENTATION

    def test_no_readme_finding_when_readme_exists(self, tmp_path):
        """A README.md being present suppresses the D-01 finding."""
        (tmp_path / "README.md").write_text("# My Project\n")
        guard = DocsGuard(root=tmp_path, doc_files=["README.md"])
        result = guard.review()
        no_readme = [f for f in result.findings if "No README" in f.title]
        assert len(no_readme) == 0

    def test_detects_missing_mentioned_file(self, tmp_path):
        """README mentioning a file that doesn't exist is flagged MEDIUM."""
        (tmp_path / "README.md").write_text(
            "Install `setup.sh` to get started.\n"
        )
        guard = DocsGuard(root=tmp_path, doc_files=["README.md"])
        result = guard.review()

        missing_ref = [f for f in result.findings if "setup.sh" in f.title]
        assert len(missing_ref) >= 1
        assert missing_ref[0].severity == Severity.MEDIUM

    def test_no_missing_file_finding_when_file_exists(self, tmp_path):
        """README mentioning a file that DOES exist is not flagged."""
        (tmp_path / "README.md").write_text("See `setup.sh`.\n")
        (tmp_path / "setup.sh").write_text("echo 'hello'\n")
        guard = DocsGuard(root=tmp_path, doc_files=["README.md"])
        result = guard.review()
        missing_ref = [f for f in result.findings if "setup.sh" in f.title]
        assert len(missing_ref) == 0

    def test_detects_implemented_route_not_documented(self, tmp_path):
        """A route decorator in source that has no doc mention is flagged MEDIUM."""
        (tmp_path / "README.md").write_text("# API\n\nNo routes here.\n")
        src = tmp_path / "app"
        src.mkdir()
        (src / "main.py").write_text(
            '@app.get("/users")\nasync def list_users(): pass\n'
        )
        guard = DocsGuard(root=tmp_path, doc_files=["README.md"])
        result = guard.review()

        undocumented = [f for f in result.findings if "/users" in f.title]
        assert len(undocumented) >= 1
        assert undocumented[0].severity == Severity.MEDIUM

    def test_detects_missing_function_docstring(self, tmp_path):
        """Public function without a docstring produces a LOW finding."""
        (tmp_path / "README.md").write_text("# Project\n")
        src = tmp_path / "mymodule.py"
        src.write_text("def my_function(x):\n    return x * 2\n")
        guard = DocsGuard(root=tmp_path, doc_files=["README.md"])
        result = guard.review()

        docstring_findings = [f for f in result.findings if "my_function" in f.title]
        assert len(docstring_findings) >= 1
        assert docstring_findings[0].severity == Severity.LOW

    def test_no_docstring_finding_when_docstring_present(self, tmp_path):
        """Function WITH a docstring produces no docstring finding."""
        (tmp_path / "README.md").write_text("# Project\n")
        src = tmp_path / "mymodule.py"
        src.write_text(
            'def documented_fn(x):\n    """Doubles x."""\n    return x * 2\n'
        )
        guard = DocsGuard(root=tmp_path, doc_files=["README.md"])
        result = guard.review()

        docstring_findings = [f for f in result.findings if "documented_fn" in f.title]
        assert len(docstring_findings) == 0

    def test_detects_missing_class_docstring(self, tmp_path):
        """Public class without docstring produces a LOW finding."""
        (tmp_path / "README.md").write_text("# Project\n")
        (tmp_path / "model.py").write_text("class MyModel:\n    pass\n")
        guard = DocsGuard(root=tmp_path, doc_files=["README.md"])
        result = guard.review()

        cls_findings = [f for f in result.findings if "MyModel" in f.title]
        assert len(cls_findings) >= 1
        assert cls_findings[0].severity == Severity.LOW

    def test_finding_ids_are_sequential_docs(self, tmp_path):
        """Finding IDs use the DOCS-NNN format."""
        guard = DocsGuard(root=tmp_path, doc_files=["README.md"])
        result = guard.review()
        for f in result.findings:
            assert f.id.startswith("DOCS-")
        ids = [f.id for f in result.findings]
        assert len(set(ids)) == len(ids)

    def test_reviewer_name_is_docsguard(self, tmp_path):
        guard = DocsGuard(root=tmp_path)
        result = guard.review()
        assert result.reviewer == "DocsGuard"

    def test_result_has_metadata(self, tmp_path):
        (tmp_path / "README.md").write_text("# Project\n")
        guard = DocsGuard(root=tmp_path, doc_files=["README.md"])
        result = guard.review()
        assert "doc_files_checked" in result.metadata
        assert "source_files_scanned" in result.metadata


# ================================================================
# Aggregator + DashboardState
# ================================================================

class TestAggregator:
    def _build_state(self, findings_a=None, findings_b=None) -> DashboardState:
        agg = Aggregator(pr=PRMetadata(repository="org/repo", pull_request="#1"))
        r1 = ReviewResult(reviewer="TestPilot")
        r1.findings.extend(findings_a or [])
        r2 = ReviewResult(reviewer="DocsGuard")
        r2.findings.extend(findings_b or [])
        agg.add_result(r1)
        agg.add_result(r2)
        return agg.build()

    def test_aggregator_merges_all_findings(self):
        state = self._build_state(
            findings_a=[_make_finding("T-001")],
            findings_b=[_make_finding("D-001", category=Category.DOCUMENTATION)],
        )
        assert state.total_findings == 2

    def test_aggregator_empty_results(self):
        state = self._build_state()
        assert state.total_findings == 0

    def test_aggregator_chaining(self):
        agg = Aggregator()
        r = ReviewResult(reviewer="X")
        result = agg.add_result(r)
        assert result is agg  # returns self

    def test_pr_metadata_propagated(self):
        state = self._build_state()
        assert state.pr.repository == "org/repo"
        assert state.pr.pull_request == "#1"

    def test_reviewer_results_stored(self):
        state = self._build_state(
            findings_a=[_make_finding()],
        )
        assert len(state.reviewer_results) == 2


class TestDashboardState:
    def _state_with(self, *findings: Finding) -> DashboardState:
        agg = Aggregator()
        r = ReviewResult(reviewer="Mixed")
        r.findings.extend(findings)
        agg.add_result(r)
        return agg.build()

    # ── Category counts ──────────────────────────────────────────

    def test_bug_count(self):
        state = self._state_with(
            _make_finding("B1", category=Category.BUG),
            _make_finding("B2", category=Category.BUG),
            _make_finding("S1", category=Category.SECURITY),
        )
        assert state.bug_count == 2
        assert state.security_count == 1

    def test_testing_and_docs_count(self):
        state = self._state_with(
            _make_finding("T1", category=Category.TESTING),
            _make_finding("D1", category=Category.DOCUMENTATION),
        )
        assert state.testing_count == 1
        assert state.docs_count == 1

    # ── Status-based lists ───────────────────────────────────────

    def test_open_findings(self):
        f1 = _make_finding("A", status=FindingStatus.OPEN)
        f2 = _make_finding("B", status=FindingStatus.APPROVED)
        state = self._state_with(f1, f2)
        assert len(state.open_findings) == 1
        assert state.open_findings[0].id == "A"

    def test_approved_rejected_fixed_pending(self):
        state = self._state_with(
            _make_finding("A", status=FindingStatus.APPROVED),
            _make_finding("B", status=FindingStatus.REJECTED),
            _make_finding("C", status=FindingStatus.FIXED),
            _make_finding("D", status=FindingStatus.PENDING_REVIEW),
        )
        assert len(state.approved_findings) == 1
        assert len(state.rejected_findings) == 1
        assert len(state.fixed_findings) == 1
        assert len(state.pending_findings) == 1

    def test_requires_human_review_list(self):
        f1 = _make_finding("H1", requires_human_approval=True)
        f2 = _make_finding("H2", requires_human_approval=False)
        state = self._state_with(f1, f2)
        assert len(state.requires_human_review) == 1
        assert state.requires_human_review[0].id == "H1"

    # ── Overall risk ─────────────────────────────────────────────

    def test_overall_risk_critical_when_critical_open(self):
        state = self._state_with(
            _make_finding("C1", severity=Severity.CRITICAL, status=FindingStatus.OPEN),
            _make_finding("H1", severity=Severity.HIGH, status=FindingStatus.OPEN),
        )
        assert state.overall_risk == "critical"

    def test_overall_risk_none_when_all_closed(self):
        f = _make_finding("F1", severity=Severity.CRITICAL, status=FindingStatus.FIXED)
        state = self._state_with(f)
        assert state.overall_risk == "none"

    def test_overall_risk_degrades_to_high(self):
        state = self._state_with(
            _make_finding("H1", severity=Severity.HIGH, status=FindingStatus.OPEN),
            _make_finding("M1", severity=Severity.MEDIUM, status=FindingStatus.OPEN),
        )
        assert state.overall_risk == "high"

    # ── Review status ────────────────────────────────────────────

    def test_review_status_pending_when_all_open(self):
        state = self._state_with(
            _make_finding("O1", status=FindingStatus.OPEN),
            _make_finding("O2", status=FindingStatus.OPEN),
        )
        assert state.review_status == "pending"

    def test_review_status_blocked_when_human_review_open(self):
        f = _make_finding("B1", requires_human_approval=True, status=FindingStatus.OPEN)
        state = self._state_with(f)
        assert state.review_status == "blocked"

    def test_review_status_in_progress_when_some_actioned(self):
        state = self._state_with(
            _make_finding("O1", status=FindingStatus.OPEN),
            _make_finding("A1", status=FindingStatus.APPROVED),
        )
        assert state.review_status == "in_progress"

    def test_review_status_complete_when_all_closed(self):
        state = self._state_with(
            _make_finding("A1", status=FindingStatus.APPROVED),
            _make_finding("F1", status=FindingStatus.FIXED),
        )
        assert state.review_status == "complete"

    def test_review_status_empty_findings(self):
        state = self._state_with()
        # No findings → all trivially non-open → complete
        assert state.review_status == "complete"

    # ── Serialisation ────────────────────────────────────────────

    def test_to_dict_keys(self):
        state = self._state_with(_make_finding())
        d = state.to_dict()
        for key in ("pr", "review_status", "overall_risk", "total_findings",
                    "summary", "findings", "final_results"):
            assert key in d, f"Missing top-level key: {key}"

    def test_to_dict_summary_keys(self):
        state = self._state_with()
        summary = state.to_dict()["summary"]
        for key in ("bugs", "security", "testing", "documentation"):
            assert key in summary

    def test_to_dict_findings_serialised(self):
        state = self._state_with(_make_finding("T-99"))
        d = state.to_dict()
        assert d["findings"][0]["id"] == "T-99"


# ================================================================
# Final results calculations
# ================================================================

class TestFinalResults:
    def _state_with(self, *findings: Finding) -> DashboardState:
        agg = Aggregator()
        r = ReviewResult(reviewer="Test")
        r.findings.extend(findings)
        agg.add_result(r)
        return agg.build()

    def test_findings_before_equals_total(self):
        state = self._state_with(
            _make_finding("A"),
            _make_finding("B"),
            _make_finding("C"),
        )
        fr = state.final_results()
        assert fr["findings_before"] == 3

    def test_findings_after_equals_open_count(self):
        state = self._state_with(
            _make_finding("A", status=FindingStatus.OPEN),
            _make_finding("B", status=FindingStatus.APPROVED),
            _make_finding("C", status=FindingStatus.FIXED),
        )
        fr = state.final_results()
        assert fr["findings_after"] == 1

    def test_fixes_applied_counts_approved_and_fixed(self):
        state = self._state_with(
            _make_finding("A", status=FindingStatus.APPROVED),
            _make_finding("B", status=FindingStatus.FIXED),
            _make_finding("C", status=FindingStatus.OPEN),
            _make_finding("D", status=FindingStatus.REJECTED),
        )
        fr = state.final_results()
        assert fr["fixes_applied"] == 2

    def test_tests_generated_is_none_by_default(self):
        state = self._state_with()
        fr = state.final_results()
        assert fr["tests_generated"] is None
        assert fr["tests_passed"] is None
        assert fr["tests_failed"] is None

    def test_final_pr_status_matches_review_status(self):
        state = self._state_with(
            _make_finding("A", status=FindingStatus.APPROVED),
        )
        fr = state.final_results()
        assert fr["final_pr_status"] == state.review_status

    def test_final_results_all_fixed(self):
        state = self._state_with(
            _make_finding("A", status=FindingStatus.FIXED),
            _make_finding("B", status=FindingStatus.FIXED),
        )
        fr = state.final_results()
        assert fr["findings_before"] == 2
        assert fr["findings_after"] == 0
        assert fr["fixes_applied"] == 2
        assert fr["final_pr_status"] == "complete"

    def test_final_results_empty(self):
        state = self._state_with()
        fr = state.final_results()
        assert fr["findings_before"] == 0
        assert fr["findings_after"] == 0
        assert fr["fixes_applied"] == 0


# ================================================================
# Approve / Reject workflow (end-to-end through state)
# ================================================================

class TestApproveRejectWorkflow:
    def test_approve_finding_via_state(self):
        f = _make_finding("W-001", status=FindingStatus.OPEN)
        state = DashboardState(findings=[f])
        # Simulate the approve action from dashboard API
        target = next(x for x in state.findings if x.id == "W-001")
        target.approve()
        assert state.approved_findings[0].id == "W-001"
        assert state.open_findings == []

    def test_reject_finding_via_state(self):
        f = _make_finding("W-002", status=FindingStatus.OPEN)
        state = DashboardState(findings=[f])
        target = next(x for x in state.findings if x.id == "W-002")
        target.reject()
        assert state.rejected_findings[0].id == "W-002"

    def test_approve_updates_risk_calculation(self):
        """After approving the only critical finding, risk should drop."""
        f = _make_finding("C-001", severity=Severity.CRITICAL, status=FindingStatus.OPEN)
        state = DashboardState(findings=[f])
        assert state.overall_risk == "critical"
        f.approve()
        # Now it's approved (not open) — risk should be none
        assert state.overall_risk == "none"

    def test_mixed_approve_reject_final_results(self):
        findings = [
            _make_finding("A", status=FindingStatus.OPEN),
            _make_finding("B", status=FindingStatus.OPEN),
            _make_finding("C", status=FindingStatus.OPEN),
        ]
        state = DashboardState(findings=findings)
        state.findings[0].approve()
        state.findings[1].reject()
        # findings[2] stays open
        fr = state.final_results()
        assert fr["findings_after"] == 1      # only C is still open
        assert fr["fixes_applied"] == 1       # only A is approved (B rejected)
