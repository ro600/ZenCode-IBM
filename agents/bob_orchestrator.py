"""
Bob Orchestrator — PRISM Workflow Entry Point
==============================================
Single callable entry point for IBM Bob to run the PRISM review pipeline.

Phase 1: scan and report findings; no files are changed.
Phase 2: apply only explicitly approved fixes, re-scan, then optionally run
pytest as the regression gate.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

from agents.aggregator import ReviewReport, run_review
from agents.fix_agent import apply_fixes


def run_regression_tests(repo_root: Path) -> dict[str, Any]:
    """Run the repository test suite and return structured execution evidence."""
    completed = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "-q"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    return {
        "returncode": completed.returncode,
        "passed": completed.returncode == 0,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def run_prism_workflow(
    target_dir: Path,
    repo_root: Path,
    approved_rule_ids: list[str] | None = None,
    run_tests: bool = False,
) -> dict[str, Any]:
    """Run the PRISM review pipeline.

    ``approved_rule_ids=None`` performs a read-only review.
    Passing approved IDs applies only those fixes, then re-scans.
    ``run_tests=True`` runs the repository regression suite after the fix phase.
    """
    pre_fix_report: ReviewReport = run_review(target_dir)

    if approved_rule_ids is None:
        return {
            "pre_fix_report": pre_fix_report,
            "fixes_applied": None,
            "post_fix_report": None,
            "regression_clean": None,
            "test_result": None,
        }

    fixes_applied = apply_fixes(approved_rule_ids, repo_root)
    post_fix_report: ReviewReport = run_review(target_dir)

    test_result = run_regression_tests(repo_root) if run_tests else None
    regression_clean = not post_fix_report.blocks_merge
    if test_result is not None:
        regression_clean = regression_clean and bool(test_result["passed"])

    return {
        "pre_fix_report": pre_fix_report,
        "fixes_applied": fixes_applied,
        "approved_rule_ids": set(approved_rule_ids),
        "post_fix_report": post_fix_report,
        "regression_clean": regression_clean,
        "test_result": test_result,
    }


def main() -> None:
    """Interactive CLI wrapper for the two-phase PRISM workflow."""
    import argparse

    parser = argparse.ArgumentParser(description="PRISM — Bob PR Guardian review pipeline")
    parser.add_argument("target_dir", type=Path, help="Directory to scan")
    parser.add_argument(
        "--fix", nargs="*", metavar="RULE_ID",
        help="Rule IDs to fix (e.g. S-01 S-02 L-01). Omit to scan only.",
    )
    parser.add_argument(
        "--run-tests", action="store_true",
        help="Run pytest after approved fixes.",
    )
    args = parser.parse_args()

    target_dir = args.target_dir.resolve()
    repo_root = Path(".").resolve()

    print(f"\n{'=' * 60}")
    print("  PRISM Review — Phase 1: Scan")
    print(f"{'=' * 60}\n")

    result = run_prism_workflow(target_dir, repo_root, approved_rule_ids=None)
    report: ReviewReport = result["pre_fix_report"]
    print(report.to_markdown())

    if args.fix is not None:
        approved = args.fix if args.fix else list(
            {f.rule_id for f in report.findings if f.severity in ("CRITICAL", "HIGH")}
        )
        print(f"\n{'=' * 60}")
        print(f"  PRISM Review — Phase 2: Applying fixes for {approved}")
        print(f"{'=' * 60}\n")

        result2 = run_prism_workflow(
            target_dir,
            repo_root,
            approved_rule_ids=approved,
            run_tests=args.run_tests,
        )
        print("Fixes applied:", result2["fixes_applied"])
        print()
        print(result2["post_fix_report"].to_markdown())

        if result2["test_result"] is not None:
            print("\nRegression tests:")
            print(result2["test_result"]["stdout"])
            if result2["test_result"]["stderr"]:
                print(result2["test_result"]["stderr"], file=sys.stderr)

        print("Regression clean:", result2["regression_clean"])
        sys.exit(0 if result2["regression_clean"] else 1)

    sys.exit(1 if report.blocks_merge else 0)


if __name__ == "__main__":
    main()
