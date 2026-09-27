"""
PreVise Dashboard — Flask application

Exposes the dashboard UI and a thin REST API so the frontend can:
  - Load the current DashboardState
  - Approve / reject individual findings
  - Trigger a fresh review run

Run locally::

    python -m prism.dashboard.app

Or via the helper script::

    python run_dashboard.py
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, render_template, abort, request

from prism.dashboard.aggregator import Aggregator, DashboardState, PRMetadata
from prism.models import Finding, FindingStatus, Category, Severity

# Snehansha's agents
from agents.sentinel import scan_directory as sentinel_scan
from agents.logic import scan_directory as logic_scan

# Aaryan's agents
from agents.test_agent import scan_directory as test_scan
from agents.doc_agent import scan_directory as doc_scan

# ------------------------------------------------------------------ #
# App factory                                                          #
# ------------------------------------------------------------------ #

TEMPLATE_DIR = Path(__file__).parent / "templates"
STATIC_DIR = Path(__file__).parent / "static"


def create_app(
    repo_root: str | Path = ".",
    pr_metadata: PRMetadata | None = None,
) -> Flask:
    """
    Create and configure the PRISM dashboard Flask app.

    Parameters
    ----------
    repo_root:
        Path to the repository being reviewed.  TestPilot and DocsGuard
        will scan this directory.
    pr_metadata:
        Optional PR context (repo name, PR number, etc.).
    """
    app = Flask(
        __name__,
        template_folder=str(TEMPLATE_DIR),
        static_folder=str(STATIC_DIR),
    )
    # Always read templates from disk — prevents stale cached HTML after restarts
    app.config["TEMPLATES_AUTO_RELOAD"] = True
    app.jinja_env.auto_reload = True

    repo_root = Path(repo_root).resolve()
    _pr = pr_metadata or PRMetadata()

    # In-memory state — rebuilt on demand or on startup
    _state: dict[str, Any] = {"dashboard": None, "repo_root": repo_root, "pr": _pr}

    def _run_pytest(root: Path) -> dict[str, Any]:
        """Run pytest in the target repo and return test counts."""
        tests_dir = root / "tests"
        if not tests_dir.is_dir():
            return {"generated": None, "passed": None, "failed": None}
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pytest", str(tests_dir), "-q", "--tb=no", "--no-header"],
                cwd=str(root),
                capture_output=True,
                text=True,
                timeout=60,
            )
            stdout = result.stdout + result.stderr
            # Parse "X passed, Y failed" from pytest summary line
            import re
            passed = failed = 0
            m_pass = re.search(r"(\d+) passed", stdout)
            m_fail = re.search(r"(\d+) failed", stdout)
            m_xfail = re.search(r"(\d+) xfailed", stdout)
            if m_pass:
                passed = int(m_pass.group(1))
            if m_fail:
                failed = int(m_fail.group(1))
            # xfailed counts as passing (expected failures)
            if m_xfail:
                passed += int(m_xfail.group(1))
            total = passed + failed
            return {"generated": total if total > 0 else None, "passed": passed, "failed": failed}
        except Exception:
            return {"generated": None, "passed": None, "failed": None}

    def _build_state() -> DashboardState:
        from prism.models import ReviewResult
        current_pr   = _state["pr"]
        current_root = _state["repo_root"]
        agg = Aggregator(pr=current_pr)

        # Run all four agents and wrap their findings into ReviewResult objects
        for agent_name, scan_fn in [
            ("Sentinel", sentinel_scan),
            ("Logic",    logic_scan),
            ("TestAgent", test_scan),
            ("DocAgent",  doc_scan),
        ]:
            raw = scan_fn(current_root)
            result = ReviewResult(reviewer=agent_name)
            for f in raw:
                # Map agent Finding -> prism Finding
                sev_map = {
                    "CRITICAL": Severity.CRITICAL,
                    "HIGH":     Severity.HIGH,
                    "MEDIUM":   Severity.MEDIUM,
                    "LOW":      Severity.LOW,
                    "INFO":     Severity.INFO,
                }
                cat_map = {
                    "Sentinel":  Category.SECURITY,
                    "Logic":     Category.BUG,
                    "TestAgent": Category.TESTING,
                    "DocAgent":  Category.DOCUMENTATION,
                }
                result.findings.append(Finding(
                    id=f"{f.rule_id}-{f.line}",
                    category=cat_map.get(agent_name, Category.BUG),
                    severity=sev_map.get(f.severity, Severity.MEDIUM),
                    title=f.message,
                    description=f.message,
                    file=f.file,
                    line=f.line,
                    evidence=f.snippet or None,
                    suggested_fix=f.fix_hint or None,
                    requires_human_approval=f.severity in ("CRITICAL", "HIGH"),
                    status=FindingStatus.OPEN,
                ))
            agg.add_result(result)

        state = agg.build()
        # Run pytest and attach test counts to state
        test_counts = _run_pytest(current_root)
        state.test_counts = test_counts
        _state["dashboard"] = state
        return state

    def _get_state() -> DashboardState:
        if _state["dashboard"] is None:
            return _build_state()
        return _state["dashboard"]

    # ---------------------------------------------------------------- #
    # UI route                                                           #
    # ---------------------------------------------------------------- #

    @app.route("/")
    def index():
        """Serve the dashboard SPA."""
        return render_template("dashboard.html")

    # ---------------------------------------------------------------- #
    # API — state                                                        #
    # ---------------------------------------------------------------- #

    def _enrich(d: dict) -> dict:
        """Add repo_root to any state dict so the UI can show it."""
        d["repo_root"] = str(_state["repo_root"])
        return d

    @app.route("/api/state")
    def api_state():
        """Return the full DashboardState as JSON."""
        return jsonify(_enrich(_get_state().to_dict()))

    @app.route("/api/refresh", methods=["POST"])
    def api_refresh():
        """Re-run all reviewers and return fresh state."""
        state = _build_state()
        return jsonify(_enrich(state.to_dict()))

    # ---------------------------------------------------------------- #
    # API — finding actions                                              #
    # ---------------------------------------------------------------- #

    # ---------------------------------------------------------------- #
    # API — configure                                                    #
    # ---------------------------------------------------------------- #

    @app.route("/api/configure", methods=["POST"])
    def api_configure():
        """Accept new PR config from the setup form and rebuild state."""
        body = request.get_json(force=True, silent=True) or {}
        new_root = Path(body.get("repo_root", ".")).resolve()
        if not new_root.is_dir():
            return jsonify({"error": f"Path not found: {new_root}"}), 400

        _state["repo_root"] = new_root
        _state["pr"] = PRMetadata(
            repository=body.get("repository", ""),
            pull_request=body.get("pull_request", ""),
            branch=body.get("branch", ""),
            author=body.get("author", ""),
        )
        _state["dashboard"] = None   # force rebuild on next request
        state = _build_state()
        return jsonify(_enrich(state.to_dict()))

    @app.route("/api/findings/<finding_id>/approve", methods=["POST"])
    def api_approve(finding_id: str):
        """Approve a finding (mark fix as accepted)."""
        finding = _find_or_404(_get_state(), finding_id)
        finding.approve()
        return jsonify({"id": finding_id, "status": finding.status.value})

    @app.route("/api/findings/<finding_id>/reject", methods=["POST"])
    def api_reject(finding_id: str):
        """Reject a finding fix."""
        finding = _find_or_404(_get_state(), finding_id)
        finding.reject()
        return jsonify({"id": finding_id, "status": finding.status.value})

    @app.route("/api/findings/<finding_id>/fix", methods=["POST"])
    def api_fix(finding_id: str):
        """Mark a finding as fixed."""
        finding = _find_or_404(_get_state(), finding_id)
        finding.mark_fixed()
        return jsonify({"id": finding_id, "status": finding.status.value})

    # ---------------------------------------------------------------- #
    # API — final results                                                #
    # ---------------------------------------------------------------- #

    @app.route("/api/results")
    def api_results():
        """Return the Final Results summary."""
        return jsonify(_get_state().final_results())

    # ---------------------------------------------------------------- #
    # Helper                                                             #
    # ---------------------------------------------------------------- #

    def _find_or_404(state: DashboardState, finding_id: str) -> Finding:
        for f in state.findings:
            if f.id == finding_id:
                return f
        abort(404, description=f"Finding '{finding_id}' not found.")

    # Seed state on startup so first page load is fast
    _build_state()

    return app


# ------------------------------------------------------------------ #
# Entry point                                                          #
# ------------------------------------------------------------------ #

if __name__ == "__main__":
    port = int(os.environ.get("PRISM_PORT", 5000))
    repo = os.environ.get("PRISM_REPO_ROOT", ".")
    pr = PRMetadata(
        repository=os.environ.get("PRISM_REPO", ""),
        pull_request=os.environ.get("PRISM_PR", ""),
        branch=os.environ.get("PRISM_BRANCH", ""),
        author=os.environ.get("PRISM_AUTHOR", ""),
    )
    application = create_app(repo_root=repo, pr_metadata=pr)
    application.run(host="0.0.0.0", port=port, debug=False)
