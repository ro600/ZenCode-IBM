"""
Shared data structures for PRISM review findings.

All reviewers (Sentinel, Logic, TestPilot, DocsGuard) produce Finding objects
that flow through the Aggregator into the Dashboard.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional
import json


class Severity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class Category(str, Enum):
    BUG = "bug"
    SECURITY = "security"
    TESTING = "testing"
    DOCUMENTATION = "documentation"


class FindingStatus(str, Enum):
    OPEN = "open"
    APPROVED = "approved"
    REJECTED = "rejected"
    FIXED = "fixed"
    PENDING_REVIEW = "pending_review"


@dataclass
class Finding:
    """A single review finding produced by any PRISM reviewer."""

    id: str
    category: Category
    severity: Severity
    title: str
    description: str
    file: Optional[str] = None
    line: Optional[int] = None
    evidence: Optional[str] = None
    suggested_fix: Optional[str] = None
    fix_recommendation: Optional[str] = None
    requires_human_approval: bool = False
    status: FindingStatus = FindingStatus.OPEN

    # ------------------------------------------------------------------ #
    # Serialisation                                                        #
    # ------------------------------------------------------------------ #

    def to_dict(self) -> dict:
        d = asdict(self)
        d["category"] = self.category.value
        d["severity"] = self.severity.value
        d["status"] = self.status.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "Finding":
        return cls(
            id=data["id"],
            category=Category(data["category"]),
            severity=Severity(data["severity"]),
            title=data["title"],
            description=data["description"],
            file=data.get("file"),
            line=data.get("line"),
            evidence=data.get("evidence"),
            suggested_fix=data.get("suggested_fix"),
            fix_recommendation=data.get("fix_recommendation"),
            requires_human_approval=data.get("requires_human_approval", False),
            status=FindingStatus(data.get("status", "open")),
        )

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    # ------------------------------------------------------------------ #
    # Status helpers                                                       #
    # ------------------------------------------------------------------ #

    def approve(self) -> None:
        self.status = FindingStatus.APPROVED

    def reject(self) -> None:
        self.status = FindingStatus.REJECTED

    def mark_fixed(self) -> None:
        self.status = FindingStatus.FIXED

    def flag_for_review(self) -> None:
        self.status = FindingStatus.PENDING_REVIEW
        self.requires_human_approval = True


@dataclass
class ReviewResult:
    """Aggregated output returned by a single reviewer."""

    reviewer: str
    findings: list[Finding] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "reviewer": self.reviewer,
            "findings": [f.to_dict() for f in self.findings],
            "metadata": self.metadata,
        }

    @property
    def finding_count(self) -> int:
        return len(self.findings)

    def findings_by_severity(self, severity: Severity) -> list[Finding]:
        return [f for f in self.findings if f.severity == severity]

    def findings_by_category(self, category: Category) -> list[Finding]:
        return [f for f in self.findings if f.category == category]
