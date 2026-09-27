"""
run_dashboard.py — Quick-start launcher for the PRISM Dashboard.

Usage::

    python run_dashboard.py

Environment variables (all optional):

    PRISM_REPO_ROOT   Path to the repository to review  (default: current dir)
    PRISM_PORT        Port to bind                       (default: 5000)
    PRISM_REPO        Repository name shown in the UI    (default: "")
    PRISM_PR          Pull-request identifier            (default: "")
    PRISM_BRANCH      Branch name                        (default: "")
    PRISM_AUTHOR      PR author                          (default: "")
"""

import os
from prism.dashboard.app import create_app
from prism.dashboard.aggregator import PRMetadata

if __name__ == "__main__":
    port = int(os.environ.get("PRISM_PORT", 5000))
    repo = os.environ.get("PRISM_REPO_ROOT", ".")
    pr = PRMetadata(
        repository=os.environ.get("PRISM_REPO", ""),
        pull_request=os.environ.get("PRISM_PR", ""),
        branch=os.environ.get("PRISM_BRANCH", ""),
        author=os.environ.get("PRISM_AUTHOR", ""),
    )
    app = create_app(repo_root=repo, pr_metadata=pr)
    print(f"  PRISM Dashboard running at  http://localhost:{port}")
    app.run(host="0.0.0.0", port=port, debug=False)