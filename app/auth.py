"""Auth utilities.

Intentional Issues:
  BUG-3 (Security): SECRET_KEY is hardcoded — must come from env var.
  BUG-4 (Security): JWT algorithm is HS256 with a weak, hardcoded key.
"""
from datetime import datetime, timedelta, timezone
from jose import jwt

# BUG-3: hardcoded secret
SECRET_KEY = "super_secret_key_1234"   # noqa: S105
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60


def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode["exp"] = expire
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict:
    # BUG-4: no verification of audience/issuer, exception not handled
    return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
