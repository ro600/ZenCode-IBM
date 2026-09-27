"""
PRISM Dashboard — Aggregator

Collects ReviewResult objects from all available reviewers and merges
them into a single DashboardState that the dashboard reads.

Reviewers (TestPilot, DocsGuard, and future Person 1 reviewers) are
registered here.  The Aggregator is the only place that knows about
individual reviewers — the dashboard only talks to the Aggregator.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from prism.models import (
    Category,
    Finding,
    FindingStatus,
    ReviewResult,
    Severity,
)


# ------------------------------------------------------------------ #
# PR metadata                                                          #
# ------------------------------------------------------------------ #


@dataclass
class PRMetadata:
    """Lightweight descriptor of the pull request being reviewed."""

    repository: str = ""
    pull_request: str = ""
    branch: str = ""
    author: str = ""
    base_branch: str = "main"


# ------------------------------------------------------------------ #
# Dashboard state                                                      #
# ------------------------------------------------------------------ #


@dataclass
class DashboardState:
    """
    The complete state exposed to the dashboard.

    Built by the Aggregator from one or more ReviewResult objects.
    """

    pr: PRMetadata = field(default_factory=PRMetadata)
    findings: list[Finding] = field(default_factory=list)
    reviewer_results: list[ReviewResult] = field(default_factory=list)
    # Populated by the Flask app after running pytest on the target repo
    test_counts: dict = field(default_factory=lambda: {"generated": None, "passed": None, "failed": None})

    # ---------------------------------------------------------------- #
    # Derived properties used by the dashboard                          #
    # ---------------------------------------------------------------- #

    @property
    def total_findings(self) -> int:
        return len(self.findings)

    @property
    def open_findings(self) -> list[Finding]:
        return [f for f in self.findings if f.status == FindingStatus.OPEN]

    @property
    def approved_findings(self) -> list[Finding]:
        return [f for f in self.findings if f.status == FindingStatus.APPROVED]

    @property
    def rejected_findings(self) -> list[Finding]:
        return [f for f in self.findings if f.status == FindingStatus.REJECTED]

    @property
    def fixed_findings(self) -> list[Finding]:
        return [f for f in self.findings if f.status == FindingStatus.FIXED]

    @property
    def pending_findings(self) -> list[Finding]:
        return [f for f in self.findings if f.status == FindingStatus.PENDING_REVIEW]

    @property
    def requires_human_review(self) -> list[Finding]:
        return [f for f in self.findings if f.requires_human_approval]

    # ---------------------------------------------------------------- #
    # Counts by category (for the Finding Summary panel)               #
    # ---------------------------------------------------------------- #

    def count_by_category(self, category: Category) -> int:
        return sum(1 for f in self.findings if f.category == category)

    @property
    def bug_count(self) -> int:
        return self.count_by_category(Category.BUG)

    @property
    def security_count(self) -> int:
        return self.count_by_category(Category.SECURITY)

    @property
    def testing_count(self) -> int:
        return self.count_by_category(Category.TESTING)

    @property
    def docs_count(self) -> int:
        return self.count_by_category(Category.DOCUMENTATION)

    # ---------------------------------------------------------------- #
    # Overall risk                                                       #
    # ---------------------------------------------------------------- #

    @property
    def overall_risk(self) -> str:
        """
        Derive an overall risk label from the highest-severity open finding.

        Returns one of: "critical", "high", "medium", "low", "none".
        """
        order = [
            Severity.CRITICAL,
            Severity.HIGH,
            Severity.MEDIUM,
            Severity.LOW,
            Severity.INFO,
        ]
        open_severities = {f.severity for f in self.open_findings}
        for sev in order:
            if sev in open_severities:
                return sev.value
        return "none"

    # ---------------------------------------------------------------- #
    # Review status                                                      #
    # ---------------------------------------------------------------- #

    @property
    def review_status(self) -> str:
        """
        Human-readable review status.

        - "pending"    — no findings have been actioned yet
        - "in_progress" — some findings have been approved/rejected
        - "complete"   — all findings have a non-open status
        - "blocked"    — one or more findings require human approval
        """
        if any(f.requires_human_approval and f.status == FindingStatus.OPEN
               for f in self.findings):
            return "blocked"
        if all(f.status != FindingStatus.OPEN for f in self.findings):
            return "complete"
        if any(f.status != FindingStatus.OPEN for f in self.findings):
            return "in_progress"
        return "pending"

    # ---------------------------------------------------------------- #
    # Final results                                                      #
    # ---------------------------------------------------------------- #

    def final_results(self) -> dict:
        """Summary dict for the Final Results panel."""
        tc = self.test_counts
        return {
            "findings_before": self.total_findings,
            "findings_after": len(self.open_findings),
            "fixes_applied": len(self.fixed_findings) + len(self.approved_findings),
            "tests_generated": tc.get("generated"),
            "tests_passed":    tc.get("passed"),
            "tests_failed":    tc.get("failed"),
            "final_pr_status": self.review_status,
        }

    # ---------------------------------------------------------------- #
    # Serialisation                                                      #
    # ---------------------------------------------------------------- #

    def to_dict(self) -> dict:
        return {
            "pr": {
                "repository":  self.pr.repository,
                "pull_request": self.pr.pull_request,
                "branch":      self.pr.branch,
                "author":      self.pr.author,
                "base_branch": self.pr.base_branch,
            },
            "review_status": self.review_status,
            "overall_risk": self.overall_risk,
            "total_findings": self.total_findings,
            "summary": {
                "bugs": self.bug_count,
                "security": self.security_count,
                "testing": self.testing_count,
                "documentation": self.docs_count,
            },
            "findings": [f.to_dict() for f in self.findings],
            "final_results": self.final_results(),
        }


# ------------------------------------------------------------------ #
# Aggregator                                                           #
# ------------------------------------------------------------------ #


class Aggregator:
    """
    Merges ReviewResult objects from all registered reviewers into a
    single DashboardState.

    Example::

        agg = Aggregator(pr=PRMetadata(repository="org/repo", pull_request="#42"))
        agg.add_result(TestPilot(root=".").review())
        agg.add_result(DocsGuard(root=".").review())
        state = agg.build()
    """

    def __init__(self, pr: Optional[PRMetadata] = None) -> None:
        self._pr = pr or PRMetadata()
        self._results: list[ReviewResult] = []

    def add_result(self, result: ReviewResult) -> "Aggregator":
        """Register a ReviewResult from a reviewer. Returns self for chaining."""
        self._results.append(result)
        return self

    def build(self) -> DashboardState:
        """Merge all registered results into a DashboardState."""
        all_findings: list[Finding] = []
        for result in self._results:
            all_findings.extend(result.findings)

        return DashboardState(
            pr=self._pr,
            findings=all_findings,
            reviewer_results=list(self._results),
        )
