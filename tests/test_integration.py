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
    # Files are placed at root/app/ so that fix_agent paths ("app/auth.py",
    # "app/crud.py") resolve correctly when repo_root=root.
    app_dir = root / "app"
    app_dir.mkdir()

    # Sentinel + fix_agent fixtures: patterns must match both the detection
    # regexes in agents/sentinel.py AND the exact string replacements in
    # agents/fix_agent.py so the full scan→fix→rescan cycle works end-to-end.
    (app_dir / "auth.py").write_text(
        'SECRET_KEY = "super_secret_key_1234"   # noqa: S105\n'
        "\n"
        "def decode_access_token(token):\n"
        "    # BUG-4: no verification of audience/issuer, exception not handled\n"
        "    return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])\n",
        encoding="utf-8",
    )

    (app_dir / "crud.py").write_text(
        "from passlib.context import CryptContext\n"
        "from app.auth import create_access_token\n"
        "\n"
        "def get_user_by_email(db, email):\n"
        "    query = text(f\"SELECT * FROM users WHERE email = '{email}'\")  # noqa: S608\n"
        "    result = db.execute(query).fetchone()\n"
        "    return result\n"
        "\n"
        "def create_user(db, user_in):\n"
        "    db_user = dict(\n"
        "        password=user_in.password,   # BUG-2: no hashing\n"
        "    )\n"
        "    return db_user\n"
        "\n"
        "def login(db, username, password):\n"
        "    user = get_user_by_username(db, username)\n"
        "    if user.password != password:   # BUG-2: plain-text compare\n"
        "        return None\n"
        "    return create_access_token({'sub': str(user.id)})\n"
        "\n"
        "def transfer_funds(sender, receiver, amount):\n"
        "    # BUG-1: missing:  if sender.balance < amount: return False\n"
        "    sender.balance -= amount\n"
        "    receiver.balance += amount\n"
        "    return True\n"
        "\n"
        "def divide_balance(user, divisor):\n"
        "    return user.balance / divisor   # BUG-6: ZeroDivisionError when divisor == 0\n",
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
