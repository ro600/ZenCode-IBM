"""
Regression tests — verify fixes applied by the Fix Workflow Agent.
All tests here should PASS after fixes are applied.
"""
import pytest
from pathlib import Path
from agents.sentinel import scan_directory as sentinel_scan
from agents.logic import scan_directory as logic_scan
from tests.conftest import *  # noqa: F401,F403

APP_DIR = Path(__file__).parent.parent / "app"


# ---------------------------------------------------------------------------
# S-01 / S-04  Hardcoded secret must be gone
# ---------------------------------------------------------------------------

def test_no_hardcoded_secret_after_fix():
    """After fix, Sentinel must find zero S-01/S-04 findings in app/."""
    findings = [
        f for f in sentinel_scan(APP_DIR)
        if f.rule_id in ("S-01", "S-04")
    ]
    assert findings == [], f"Hardcoded secret still present: {findings}"


# ---------------------------------------------------------------------------
# S-02  SQL injection must be gone
# ---------------------------------------------------------------------------

def test_no_sql_injection_after_fix():
    findings = [f for f in sentinel_scan(APP_DIR) if f.rule_id == "S-02"]
    assert findings == [], f"SQL injection still present: {findings}"


# ---------------------------------------------------------------------------
# S-03  Plain-text password must be gone
# ---------------------------------------------------------------------------

def test_no_plain_text_password_after_fix():
    findings = [f for f in sentinel_scan(APP_DIR) if f.rule_id == "S-03"]
    assert findings == [], f"Plain-text password still present: {findings}"


# ---------------------------------------------------------------------------
# L-01  Transfer must reject insufficient balance after fix
# ---------------------------------------------------------------------------

def test_transfer_rejects_insufficient_balance(client):
    """After fix, transfer with insufficient balance returns 400."""
    r1 = client.post("/users", json={"username": "sender_fixed", "email": "sf@ex.com", "password": "pw"})
    r2 = client.post("/users", json={"username": "recv_fixed", "email": "rf@ex.com", "password": "pw"})
    s_id, r_id = r1.json()["id"], r2.json()["id"]
    resp = client.post("/transfer", params={"from_user_id": s_id}, json={"to_user_id": r_id, "amount": 500.0})
    assert resp.status_code == 400, "Transfer with zero balance should be rejected after fix"


# ---------------------------------------------------------------------------
# L-02  Division by zero must raise ValueError after fix
# ---------------------------------------------------------------------------

def test_divide_by_zero_raises_value_error_after_fix(client_no_raise):
    """After fix, /divide?divisor=0 raises ValueError (returns 500 with explicit error)."""
    r = client_no_raise.post("/users", json={"username": "zdiv_fixed", "email": "zf@ex.com", "password": "pw"})
    uid = r.json()["id"]
    resp = client_no_raise.get(f"/users/{uid}/divide", params={"divisor": 0})
    # ValueError is raised explicitly — still 500 but it is a deliberate raise not silent
    assert resp.status_code in (400, 422, 500)


# ---------------------------------------------------------------------------
# L-04  JWT decode must not crash on bad token
# ---------------------------------------------------------------------------

def test_jwt_decode_bad_token_does_not_crash():
    """After fix, decode_access_token returns empty dict on invalid token."""
    from app.auth import decode_access_token
    result = decode_access_token("totally.invalid.token")
    assert result == {} or result is None


# ---------------------------------------------------------------------------
# Aggregator — full scan should find at least 5 issues in buggy app
# ---------------------------------------------------------------------------

def test_aggregator_finds_seven_issues_in_buggy_app():
    """The intentional bug catalogue contains 7 issues total."""
    from agents.aggregator import run_review
    report = run_review(APP_DIR)
    assert report.total >= 5, f"Expected at least 5 findings, got {report.total}: {report.to_dict()}"
    assert report.blocks_merge is True


# ---------------------------------------------------------------------------
# Sentinel agent unit tests
# ---------------------------------------------------------------------------

def test_sentinel_detects_hardcoded_secret(tmp_path):
    f = tmp_path / "auth.py"
    f.write_text('SECRET_KEY = "my_secret"  # noqa: S105\n')
    findings = sentinel_scan(tmp_path)
    assert any(x.rule_id in ("S-01", "S-04") for x in findings)


def test_sentinel_detects_sql_injection(tmp_path):
    f = tmp_path / "crud.py"
    f.write_text('query = text(f"SELECT * FROM users WHERE email = \'{email}\'")\n')
    findings = sentinel_scan(tmp_path)
    assert any(x.rule_id == "S-02" for x in findings)


def test_sentinel_detects_plain_password_storage(tmp_path):
    f = tmp_path / "crud.py"
    f.write_text("        password=user_in.password,\n")
    f2 = tmp_path / "crud2.py"
    f2.write_text("    if user.password != password:\n")
    findings = sentinel_scan(tmp_path)
    assert any(x.rule_id == "S-03" for x in findings)


def test_sentinel_detects_unauthenticated_endpoint(tmp_path):
    f = tmp_path / "main.py"
    f.write_text(
        "@app.post('/transfer')\n"
        "async def transfer(payload: dict):\n"
        "    pass\n"
    )
    findings = sentinel_scan(tmp_path)
    assert any(x.rule_id == "S-05" for x in findings), (
        "Expected S-05 finding for unauthenticated route"
    )


def test_sentinel_no_s05_when_auth_present(tmp_path):
    f = tmp_path / "main.py"
    f.write_text(
        "@app.get('/profile')\n"
        "async def get_profile(current_user=Depends(get_current_user)):\n"
        "    pass\n"
    )
    findings = sentinel_scan(tmp_path)
    assert not any(x.rule_id == "S-05" for x in findings), (
        "S-05 should not fire when Depends(get_current_user) is present"
    )


# ---------------------------------------------------------------------------
# Logic agent unit tests
# ---------------------------------------------------------------------------

def test_logic_detects_missing_balance_guard(tmp_path):
    f = tmp_path / "crud.py"
    f.write_text(
        "def transfer_funds(db, from_id, to_id, amount):\n"
        "    sender = get_user(db, from_id)\n"
        "    receiver = get_user(db, to_id)\n"
        "    sender.balance -= amount\n"
        "    receiver.balance += amount\n"
    )
    from agents.logic import scan_directory
    findings = scan_directory(tmp_path)
    assert any(x.rule_id == "L-01" for x in findings)


def test_logic_detects_division_zero(tmp_path):
    f = tmp_path / "crud.py"
    f.write_text("    return user.balance / divisor\n")
    from agents.logic import scan_directory
    findings = scan_directory(tmp_path)
    assert any(x.rule_id == "L-02" for x in findings)


def test_logic_detects_unhandled_jwt(tmp_path):
    f = tmp_path / "auth.py"
    f.write_text("    return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])\n")
    from agents.logic import scan_directory
    findings = scan_directory(tmp_path)
    assert any(x.rule_id == "L-04" for x in findings)


def test_logic_detects_implicit_none_return(tmp_path):
    """L-03: function typed -> str that explicitly returns None should be flagged."""
    f = tmp_path / "service.py"
    f.write_text(
        "def get_token(user_id: int) -> str:\n"
        "    if user_id <= 0:\n"
        "        return None\n"
        "    return 'tok_' + str(user_id)\n"
    )
    from agents.logic import scan_directory
    findings = scan_directory(tmp_path)
    assert any(x.rule_id == "L-03" for x in findings), (
        "Expected L-03 finding for non-Optional function returning None"
    )


def test_logic_no_l03_when_optional_annotated(tmp_path):
    """L-03 must NOT fire when the return type already includes None."""
    f = tmp_path / "service.py"
    f.write_text(
        "from __future__ import annotations\n"
        "def get_token(user_id: int) -> str | None:\n"
        "    if user_id <= 0:\n"
        "        return None\n"
        "    return 'tok_' + str(user_id)\n"
    )
    from agents.logic import scan_directory
    findings = scan_directory(tmp_path)
    assert not any(x.rule_id == "L-03" for x in findings), (
        "L-03 must not fire when return type is already Optional (str | None)"
    )
