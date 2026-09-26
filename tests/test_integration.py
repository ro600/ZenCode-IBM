"""
End-to-end PRISM workflow tests.

These tests exercise the complete Person 1 pipeline on a temporary copy of the
intentional-bug demo code:

    Sentinel + Logic -> aggregation -> approval -> Fix Agent -> re-scan

The real repository is never modified by this test.
"""
from __future__ import annotations

from pathlib import Path

from agents.bob_orchestrator import run_prism_workflow


BUGGY_AUTH = '''\
from jose import jwt

SECRET_KEY = "super_secret_key_1234"   # noqa: S105
ALGORITHM = "HS256"


def decode_access_token(token: str) -> dict:
    # BUG-4: no verification of audience/issuer, exception not handled
    return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
'''

BUGGY_CRUD = '''\
from sqlalchemy import text


def create_user(db, user_in):
    db_user = type("User", (), {})()
    db_user.password = user_in.password   # BUG-2: no hashing
    return db_user


def login(user, password):
    if user.password != password:   # BUG-2: plain-text compare
        return None
    return "token"


def get_user_by_email(db, email):
    query = text(f"SELECT * FROM users WHERE email = '{email}'")  # noqa: S608
    result = db.execute(query).fetchone()
    return result


def transfer_funds(db, from_user_id, to_user_id, amount):
    sender = get_user(db, from_user_id)
    receiver = get_user(db, to_user_id)
    if sender is None or receiver is None:
        return False
    # BUG-1: missing:  if sender.balance < amount: return False
    sender.balance -= amount
    receiver.balance += amount
    return True


def divide_balance(db, user_id, divisor):
    user = get_user(db, user_id)
    if user is None:
        return 0.0
    return user.balance / divisor   # BUG-6: ZeroDivisionError when divisor == 0
'''


def _write_buggy_demo_repo(repo_root: Path) -> Path:
    app_dir = repo_root / "app"
    app_dir.mkdir(parents=True)
    (app_dir / "auth.py").write_text(BUGGY_AUTH, encoding="utf-8")
    (app_dir / "crud.py").write_text(BUGGY_CRUD, encoding="utf-8")
    return app_dir


def test_full_prism_review_fix_rescan_workflow(tmp_path: Path):
    """Verify scan -> approved fix -> re-scan clears all auto-fixable findings."""
    app_dir = _write_buggy_demo_repo(tmp_path)

    # Phase 1: Bob reviews the intentionally vulnerable code without changing it.
    pre = run_prism_workflow(app_dir, tmp_path)
    pre_ids = {finding.rule_id for finding in pre["pre_fix_report"].findings}

    assert {"S-01", "S-02", "S-03", "S-04", "L-01", "L-02", "L-04"} <= pre_ids
    assert pre["pre_fix_report"].blocks_merge is True
    assert pre["fixes_applied"] is None
    assert pre["post_fix_report"] is None

    # Phase 2: simulate explicit human approval of every registered auto-fix.
    approved = ["S-01", "S-02", "S-03", "S-04", "L-01", "L-02", "L-04"]
    post = run_prism_workflow(app_dir, tmp_path, approved_rule_ids=approved)

    assert all(post["fixes_applied"].values()), post["fixes_applied"]
    assert post["post_fix_report"].total == 0
    assert post["post_fix_report"].blocks_merge is False
    assert post["regression_clean"] is True

    # Verify the actual source changed to the expected safe patterns.
    auth = (app_dir / "auth.py").read_text(encoding="utf-8")
    crud = (app_dir / "crud.py").read_text(encoding="utf-8")

    assert "os.environ.get(\"JWT_SECRET_KEY\"" in auth
    assert 'jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])' in auth
    assert "try:" in auth

    assert 'text("SELECT * FROM users WHERE email = :email")' in crud
    assert 'db.execute(query, {"email": email})' in crud
    assert "pwd_context.hash(user_in.password)" in crud
    assert "pwd_context.verify(password, user.password)" in crud
    assert "if sender.balance < amount:" in crud
    assert "if divisor == 0:" in crud
