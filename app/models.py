"""SQLAlchemy ORM models.

Intentional Issues:
  BUG-1 (Logic):    transfer_funds does not check for sufficient balance before
                    debiting — allows negative balances.
  BUG-2 (Security): PASSWORD stored as plain text.
"""
from sqlalchemy import Column, Integer, String, Float, ForeignKey, Text
from sqlalchemy.orm import relationship
from app.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    email = Column(String, nullable=False)          # BUG-2: no unique constraint; used as login key elsewhere
    password = Column(String, nullable=False)       # BUG-2: plain-text password stored here
    balance = Column(Float, default=0.0)

    transactions = relationship("Transaction", back_populates="owner")


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    amount = Column(Float, nullable=False)
    description = Column(Text, default="")

    owner = relationship("User", back_populates="transactions")
