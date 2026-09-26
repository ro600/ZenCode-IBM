"""
Bob Orchestrator — PRISM Workflow Entry Point
==============================================
This module is the single callable entry point for IBM Bob to run the full
PRISM (Parallel Review and Intelligent Security Monitor) pipeline.

IBM Bob Agent-mode usage
------------------------
Phase 1 — scan only (no approved_rule_ids):

    from pathlib import Path
    from agents.bob_orchestrator import run_prism_workflow

    result = run_prism_workflow(Path("app/"), Path("."))
    print(result["pre_fix_report"].to_markdown())
    # Bob presents the report in chat and waits for developer approval

Phase 2 — apply approved fixes:

    result = run_prism_workflow(
        Path("app/"), Path("."),
        approved_rule_ids=["S-01", "S-02", "S-03", "S-04", "L-01", "L-02", "L-04"],
    )
    print(result["fixes_applied"])        # {rule_id: True/False}
    print(result["post_fix_report"].to_markdown())
    print("Clean:", not result["post_fix_report"].blocks_merge)

CLI usage
---------
    python -m agents.bob_orchestrator app/
    python -m agents.bob_orchestrator app/ --fix S-01 S-02 S-03
"""
from __future__ import annotations

import sys
from pathlib import Path

from agents.aggregator import ReviewReport, run_review
from agents.fix_agent import apply_fixes


def run_prism_workflow(
    target_dir: Path,
    repo_root: Path,
    approved_rule_ids: list[str] | None = None,
) -> dict:
    """Run the PRISM review pipeline.

    Parameters
    ----------
    target_dir:
        Directory to scan (pass ``Path("app/")`` for the demo app).
    repo_root:
        Repository root used to resolve fix-target file paths
        (pass ``Path(".")`` when running from the repo root).
    approved_rule_ids:
        If ``None``, phase 1 only — scan and return the pre-fix report.
        If a list of rule IDs, phase 2 — apply fixes, re-scan, and return
        a before/after comparison dict.

    Returns
    -------
    dict with keys:
        ``pre_fix_report``   ReviewReport before any fixes
        ``fixes_applied``    {rule_id: bool} or None (phase 1 only)
        ``post_fix_report``  ReviewReport after fixes, or None (phase 1 only)
        ``regression_clean`` True if post-fix report does not block merge
    """
    pre_fix_report: ReviewReport = run_review(target_dir)

    if approved_rule_ids is None:
        return {
            "pre_fix_report": pre_fix_report,
            "fixes_applied": None,
            "post_fix_report": None,
            "regression_clean": None,
        }

    fixes_applied = apply_fixes(approved_rule_ids, repo_root)
    post_fix_report: ReviewReport = run_review(target_dir)

    return {
        "pre_fix_report": pre_fix_report,
        "fixes_applied": fixes_applied,
        "post_fix_report": post_fix_report,
        "regression_clean": not post_fix_report.blocks_merge,
    }


def main() -> None:
    """Interactive CLI wrapper for the two-phase PRISM workflow."""
    import argparse

    parser = argparse.ArgumentParser(
        description="PRISM — Bob PR Guardian review pipeline",
        epilog="Example: python -m agents.bob_orchestrator app/",
    )
    parser.add_argument("target_dir", type=Path, help="Directory to scan")
    parser.add_argument(
        "--fix",
        nargs="*",
        metavar="RULE_ID",
        help="Rule IDs to fix (e.g. S-01 S-02 L-01). Omit to scan only.",
    )
    args = parser.parse_args()

    target_dir: Path = args.target_dir.resolve()
    repo_root: Path = Path(".").resolve()

    print(f"\n{'='*60}")
    print("  PRISM Review — Phase 1: Scan")
    print(f"{'='*60}\n")

    result = run_prism_workflow(target_dir, repo_root, approved_rule_ids=None)
    report: ReviewReport = result["pre_fix_report"]
    print(report.to_markdown())

    if args.fix is not None:
        approved = args.fix if args.fix else list(
            {f.rule_id for f in report.findings if f.severity in ("CRITICAL", "HIGH")}
        )
        print(f"\n{'='*60}")
        print(f"  PRISM Review — Phase 2: Applying fixes for {approved}")
        print(f"{'='*60}\n")

        result2 = run_prism_workflow(target_dir, repo_root, approved_rule_ids=approved)
        print("Fixes applied:", result2["fixes_applied"])
        print()
        print(result2["post_fix_report"].to_markdown())
        print("Regression clean:", result2["regression_clean"])
        sys.exit(0 if result2["regression_clean"] else 1)

    sys.exit(1 if report.blocks_merge else 0)


if __name__ == "__main__":
    main()
