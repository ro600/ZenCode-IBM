"""
PRISM Dashboard — Flask application

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

    repo_root = Path(repo_root).resolve()
    _pr = pr_metadata or PRMetadata()

    # In-memory state — rebuilt on demand or on startup
    _state: dict[str, Any] = {"dashboard": None, "repo_root": repo_root, "pr": _pr}

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

    @app.route("/api/state")
    def api_state():
        """Return the full DashboardState as JSON."""
        return jsonify(_get_state().to_dict())

    @app.route("/api/refresh", methods=["POST"])
    def api_refresh():
        """Re-run all reviewers and return fresh state."""
        state = _build_state()
        return jsonify(state.to_dict())

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
        return jsonify(state.to_dict())

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
