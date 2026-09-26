"""FastAPI application entry point."""
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db, init_db
from app import crud, schemas
from app.auth import decode_access_token


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="PRISM Demo App", version="1.0.0", lifespan=lifespan)


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/health")
def health():
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

@app.post("/users", response_model=schemas.UserOut, status_code=201)
def create_user(user_in: schemas.UserCreate, db: Session = Depends(get_db)):
    existing = crud.get_user_by_username(db, user_in.username)
    if existing:
        raise HTTPException(status_code=400, detail="Username already taken")
    return crud.create_user(db, user_in)


@app.get("/users/{user_id}", response_model=schemas.UserOut)
def get_user(user_id: int, db: Session = Depends(get_db)):
    user = crud.get_user(db, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return user


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

@app.post("/login", response_model=schemas.TokenResponse)
def login(req: schemas.LoginRequest, db: Session = Depends(get_db)):
    token = crud.login(db, req.username, req.password)
    if token is None:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return {"access_token": token}


# ---------------------------------------------------------------------------
# Transactions
# ---------------------------------------------------------------------------

@app.post("/users/{user_id}/transactions", response_model=schemas.TransactionOut, status_code=201)
def create_transaction(
    user_id: int,
    tx_in: schemas.TransactionCreate,
    db: Session = Depends(get_db),
):
    user = crud.get_user(db, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return crud.create_transaction(db, user_id, tx_in)


# ---------------------------------------------------------------------------
# Transfers
# ---------------------------------------------------------------------------

@app.post("/transfer", status_code=200)
def transfer(req: schemas.TransferRequest, from_user_id: int, db: Session = Depends(get_db)):
    ok = crud.transfer_funds(db, from_user_id, req.to_user_id, req.amount)
    if not ok:
        raise HTTPException(status_code=400, detail="Transfer failed")
    return {"message": "Transfer complete"}


# ---------------------------------------------------------------------------
# Account summary
# ---------------------------------------------------------------------------

@app.get("/users/{user_id}/summary")
def account_summary(user_id: int, db: Session = Depends(get_db)):
    return crud.get_account_summary(db, user_id)


# ---------------------------------------------------------------------------
# Divide (exposes BUG-6)
# ---------------------------------------------------------------------------

@app.get("/users/{user_id}/divide")
def divide(user_id: int, divisor: float, db: Session = Depends(get_db)):
    result = crud.divide_balance(db, user_id, divisor)
    return {"result": result}
