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

import json
import os
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, render_template, request, abort

from prism.dashboard.aggregator import Aggregator, DashboardState, PRMetadata
from prism.models import Finding, FindingStatus
from prism.reviewers.test_pilot import TestPilot
from prism.reviewers.docs_guard import DocsGuard

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
    _state: dict[str, Any] = {"dashboard": None}

    def _build_state() -> DashboardState:
        agg = Aggregator(pr=_pr)
        agg.add_result(TestPilot(root=repo_root).review())
        agg.add_result(DocsGuard(root=repo_root).review())
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
