"""
Baseline tests — verify the base app is functional before any fixes.
These tests document EXPECTED broken behaviour in the buggy codebase.
"""
import pytest
from tests.conftest import *  # noqa: F401,F403


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


# ---------------------------------------------------------------------------
# User creation
# ---------------------------------------------------------------------------

def test_create_user(client):
    resp = client.post("/users", json={
        "username": "alice",
        "email": "alice@example.com",
        "password": "secret123",
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["username"] == "alice"
    assert data["balance"] == 0.0
    assert "id" in data


def test_create_duplicate_user(client):
    client.post("/users", json={"username": "bob", "email": "bob@example.com", "password": "pw"})
    resp = client.post("/users", json={"username": "bob", "email": "bob@example.com", "password": "pw"})
    assert resp.status_code == 400


def test_get_user(client):
    resp = client.post("/users", json={"username": "carol", "email": "carol@ex.com", "password": "pw"})
    uid = resp.json()["id"]
    resp2 = client.get(f"/users/{uid}")
    assert resp2.status_code == 200
    assert resp2.json()["username"] == "carol"


def test_get_user_not_found(client):
    resp = client.get("/users/99999")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def test_login_success(client):
    client.post("/users", json={"username": "dave", "email": "dave@ex.com", "password": "mypass"})
    resp = client.post("/login", json={"username": "dave", "password": "mypass"})
    assert resp.status_code == 200
    assert "access_token" in resp.json()


def test_login_wrong_password(client):
    client.post("/users", json={"username": "eve", "email": "eve@ex.com", "password": "correct"})
    resp = client.post("/login", json={"username": "eve", "password": "wrong"})
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Transactions
# ---------------------------------------------------------------------------

def test_create_transaction(client):
    r = client.post("/users", json={"username": "frank", "email": "f@ex.com", "password": "pw"})
    uid = r.json()["id"]
    resp = client.post(f"/users/{uid}/transactions", json={"amount": 100.0, "description": "deposit"})
    assert resp.status_code == 201
    assert resp.json()["amount"] == 100.0


# ---------------------------------------------------------------------------
# BUG-1 — Transfer allows negative balance (DOCUMENTED BROKEN BASELINE)
# ---------------------------------------------------------------------------

@pytest.mark.xfail(
    reason="BUG-1 is fixed: balance check now rejects overdraft transfers (expected failure in fixed codebase)",
    strict=True,
)
def test_transfer_allows_negative_balance_bug(client):
    """
    BASELINE BUG-1: Transfer should fail when sender has insufficient balance,
    but the buggy implementation allows it, leaving sender with negative balance.
    This test documents the BROKEN behaviour before the fix.
    """
    r1 = client.post("/users", json={"username": "sender1", "email": "s1@ex.com", "password": "pw"})
    r2 = client.post("/users", json={"username": "receiver1", "email": "r1@ex.com", "password": "pw"})
    s_id, r_id = r1.json()["id"], r2.json()["id"]
    # sender has balance=0, tries to send 500 — BUG-1 allows it
    resp = client.post("/transfer", params={"from_user_id": s_id}, json={"to_user_id": r_id, "amount": 500.0})
    assert resp.status_code == 200  # BUG: should be 400


# ---------------------------------------------------------------------------
# BUG-6 — Division by zero (DOCUMENTED BROKEN BASELINE)
# ---------------------------------------------------------------------------

def test_divide_by_zero_raises_500_bug(client_no_raise):
    """BASELINE BUG-6: dividing by zero crashes with 500 (unhandled ZeroDivisionError)."""
    r = client_no_raise.post("/users", json={"username": "gina", "email": "g@ex.com", "password": "pw"})
    uid = r.json()["id"]
    resp = client_no_raise.get(f"/users/{uid}/divide", params={"divisor": 0})
    assert resp.status_code == 500  # BUG: unhandled ZeroDivisionError
