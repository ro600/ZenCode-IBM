"""
PRISM end-to-end integration test.

This test uses a temporary intentionally vulnerable repository so that the
production app can remain fixed.  It verifies the Person 1 review flow:
scan -> findings -> approved fixes -> re-scan.

The fixture deliberately matches the patterns implemented by Sentinel and
Logic, especially L-01 (transfer_funds + sender.balance -= amount).
"""
from pathlib import Path

from agents.bob_orchestrator import run_prism_workflow


def _write_buggy_demo_repo(root: Path) -> Path:
    app_dir = root / "demo_app"
    app_dir.mkdir()

    # Sentinel fixtures: hardcoded secret, SQL injection, plaintext password,
    # and an insecure configuration.
    (app_dir / "security_demo.py").write_text(
        """
SECRET_KEY = "demo-hardcoded-secret"

def find_user(user_id):
    query = f"SELECT * FROM users WHERE id = {user_id}"
    return query

def create_user(password):
    user_record = {"password": password}
    return user_record

DEBUG = True
""",
        encoding="utf-8",
    )

    # Logic fixtures: use the exact patterns expected by agents/logic.py.
    # L-01 requires a function named transfer_funds and a sender.balance -= amount
    # mutation without a preceding sender.balance < amount guard.
    (app_dir / "logic_demo.py").write_text(
        """
def transfer_funds(sender, receiver, amount):
    sender.balance -= amount
    receiver.balance += amount
    return True


def calculate_ratio(value, divisor):
    return value / divisor


def decode_token(token):
    return jwt.decode(token, "secret", algorithms=["HS256"])
""",
        encoding="utf-8",
    )

    return app_dir


def test_full_prism_review_fix_rescan_workflow(tmp_path: Path):
    """
    Verify the complete Person 1 workflow on an isolated vulnerable fixture.

    The production app is intentionally NOT modified by this test.
    """
    app_dir = _write_buggy_demo_repo(tmp_path)

    # First pass: analyse only.
    pre = run_prism_workflow(app_dir, tmp_path)
    pre_ids = {finding.rule_id for finding in pre["pre_fix_report"].findings}

    expected = {"S-01", "S-02", "S-03", "S-04", "L-01", "L-02", "L-04"}
    assert expected <= pre_ids, (
        f"Expected all seven auto-fixable rules, but got: {sorted(pre_ids)}"
    )

    # Second pass: explicitly approve the seven auto-fixable findings.
    approved = sorted(expected)
    post = run_prism_workflow(
        app_dir,
        tmp_path,
        approved_rule_ids=approved,
    )

    post_ids = {finding.rule_id for finding in post["post_fix_report"].findings}

    # Every approved rule should disappear after the fix.
    assert not (expected & post_ids), (
        f"Approved findings remain after fix: {sorted(expected & post_ids)}"
    )

    # The workflow must report that the approved fixes were applied.
    assert set(post["approved_rule_ids"]) == expected
