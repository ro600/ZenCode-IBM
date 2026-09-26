"""
Review Aggregator
=================
Merges findings from Sentinel and Logic agents, deduplicates, classifies
risk, and produces a structured review report.

Risk matrix:
  CRITICAL  →  must block merge
  HIGH      →  should block merge
  MEDIUM    →  fix before next release
  LOW/INFO  →  advisory
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agents.sentinel import Finding, scan_directory as sentinel_scan
from agents.logic import scan_directory as logic_scan


_SEVERITY_ORDER = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "INFO": 4}


@dataclass
class ReviewReport:
    findings: list[Finding] = field(default_factory=list)

    # -----------------------------------------------------------------------
    # Derived properties
    # -----------------------------------------------------------------------

    @property
    def total(self) -> int:
        return len(self.findings)

    @property
    def by_severity(self) -> Counter:
        return Counter(f.severity for f in self.findings)

    @property
    def blocks_merge(self) -> bool:
        """True when any CRITICAL or HIGH finding is present."""
        return any(f.severity in ("CRITICAL", "HIGH") for f in self.findings)

    @property
    def sorted_findings(self) -> list[Finding]:
        return sorted(self.findings, key=lambda f: _SEVERITY_ORDER.get(f.severity, 9))

    # -----------------------------------------------------------------------
    # Serialisation
    # -----------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "blocks_merge": self.blocks_merge,
            "by_severity": dict(self.by_severity),
            "findings": [f.to_dict() for f in self.sorted_findings],
        }

    def to_markdown(self) -> str:
        lines = ["# PRISM Review Report", ""]
        lines.append(f"**Total findings:** {self.total}  ")
        lines.append(f"**Merge blocked:** {'YES [BLOCKED]' if self.blocks_merge else 'NO [CLEAN]'}  ")
        lines.append("")

        # Summary table
        lines.append("## Severity Summary")
        lines.append("")
        lines.append("| Severity | Count |")
        lines.append("|----------|-------|")
        for sev in ("CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"):
            count = self.by_severity.get(sev, 0)
            if count:
                lines.append(f"| {sev} | {count} |")
        lines.append("")

        # Detail
        lines.append("## Findings")
        lines.append("")
        for i, f in enumerate(self.sorted_findings, 1):
            lines.append(f"### {i}. [{f.severity}] {f.rule_id} — {f.message}")
            lines.append(f"- **File:** `{f.file}` line {f.line}")
            lines.append(f"- **Agent:** {f.agent}")
            if f.snippet:
                lines.append(f"- **Code:** `{f.snippet}`")
            if f.fix_hint:
                lines.append(f"- **Fix:** {f.fix_hint}")
            lines.append("")

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_review(target_dir: Path) -> ReviewReport:
    """Run Sentinel + Logic agents in parallel (sequential here for simplicity)
    and return an aggregated ReviewReport.

    In the full Bob demo, Sentinel and Logic are spawned as parallel subagents.
    """
    report = ReviewReport()

    security_findings = sentinel_scan(target_dir)
    logic_findings = logic_scan(target_dir)

    # Deduplicate by (file, line, rule_id)
    seen: set[tuple] = set()
    for f in security_findings + logic_findings:
        key = (f.file, f.line, f.rule_id)
        if key not in seen:
            seen.add(key)
            report.findings.append(f)

    return report
