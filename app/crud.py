"""Core business logic.

Intentional Issues:
  BUG-1 (Logic):    transfer_funds — no balance check; allows negative balance.
  BUG-5 (Logic):    get_user_by_email — raw string interpolation in query (SQL injection).
  BUG-6 (Logic):    divide_balance — no zero-division guard.
  BUG-7 (Docs):     get_account_summary docstring claims it returns JSON but returns a dict.
"""
from sqlalchemy.orm import Session
from sqlalchemy import text
from app import models, schemas
from app.auth import create_access_token


# ---------------------------------------------------------------------------
# User CRUD
# ---------------------------------------------------------------------------

def create_user(db: Session, user_in: schemas.UserCreate) -> models.User:
    """Create a new user. Password stored as plain text (BUG-2)."""
    db_user = models.User(
        username=user_in.username,
        email=user_in.email,
        password=user_in.password,   # BUG-2: no hashing
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user


def get_user(db: Session, user_id: int) -> models.User | None:
    return db.query(models.User).filter(models.User.id == user_id).first()


def get_user_by_username(db: Session, username: str) -> models.User | None:
    return db.query(models.User).filter(models.User.username == username).first()


def get_user_by_email(db: Session, email: str) -> models.User | None:
    """BUG-5: raw f-string SQL — vulnerable to SQL injection."""
    query = text(f"SELECT * FROM users WHERE email = '{email}'")  # noqa: S608
    result = db.execute(query).fetchone()
    return result  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def login(db: Session, username: str, password: str) -> str | None:
    """Return JWT token if credentials match (plain-text compare — BUG-2)."""
    user = get_user_by_username(db, username)
    if user is None:
        return None
    if user.password != password:   # BUG-2: plain-text compare
        return None
    return create_access_token({"sub": str(user.id)})


# ---------------------------------------------------------------------------
# Transactions & Transfers
# ---------------------------------------------------------------------------

def create_transaction(
    db: Session, user_id: int, tx_in: schemas.TransactionCreate
) -> models.Transaction:
    tx = models.Transaction(
        owner_id=user_id,
        amount=tx_in.amount,
        description=tx_in.description or "",
    )
    db.add(tx)
    db.commit()
    db.refresh(tx)
    return tx


def transfer_funds(
    db: Session, from_user_id: int, to_user_id: int, amount: float
) -> bool:
    """Transfer `amount` from one user to another.

    BUG-1: No balance check — sender's balance can go negative.
    """
    sender = get_user(db, from_user_id)
    receiver = get_user(db, to_user_id)
    if sender is None or receiver is None:
        return False
    # BUG-1: missing:  if sender.balance < amount: return False
    sender.balance -= amount
    receiver.balance += amount
    db.commit()
    return True


def divide_balance(db: Session, user_id: int, divisor: float) -> float:
    """BUG-6: no zero-division guard."""
    user = get_user(db, user_id)
    if user is None:
        return 0.0
    return user.balance / divisor   # BUG-6: ZeroDivisionError when divisor == 0


# ---------------------------------------------------------------------------
# Account summary
# ---------------------------------------------------------------------------

def get_account_summary(db: Session, user_id: int) -> dict:
    """Returns a JSON response with user balance and transaction count.

    BUG-7 (Docs): docstring says 'JSON response' but actually returns a plain dict.
    Caller must serialise. README also documents wrong field name 'tx_count'
    instead of 'transaction_count'.
    """
    user = get_user(db, user_id)
    if user is None:
        return {}
    tx_count = (
        db.query(models.Transaction)
        .filter(models.Transaction.owner_id == user_id)
        .count()
    )
    return {"balance": user.balance, "transaction_count": tx_count}
