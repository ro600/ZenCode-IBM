"""Pydantic schemas for request/response validation."""
from pydantic import BaseModel
from typing import Optional


class UserCreate(BaseModel):
    username: str
    email: str
    password: str


class UserOut(BaseModel):
    id: int
    username: str
    email: str
    balance: float

    model_config = {"from_attributes": True}


class TransactionCreate(BaseModel):
    amount: float
    description: Optional[str] = ""


class TransactionOut(BaseModel):
    id: int
    owner_id: int
    amount: float
    description: str

    model_config = {"from_attributes": True}


class TransferRequest(BaseModel):
    to_user_id: int
    amount: float


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
