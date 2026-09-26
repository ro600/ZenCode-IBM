# Intentional Bugs Catalogue

This file documents the 7 intentional issues seeded into the demo application
for the Bob PR Guardian demonstration.

| # | ID | Agent | Severity | File | Description |
|---|-----|-------|----------|------|-------------|
| 1 | L-01 | Logic | HIGH | `app/crud.py` | `transfer_funds` debits sender without checking sufficient balance |
| 2 | S-03 | Sentinel | HIGH | `app/crud.py` | Password stored and compared as plain text (no hashing) |
| 3 | S-01 | Sentinel | CRITICAL | `app/auth.py` | `SECRET_KEY` hardcoded as string literal |
| 4 | S-04 | Sentinel | CRITICAL | `app/auth.py` | JWT secret is weak and hardcoded |
| 5 | S-02 | Sentinel | CRITICAL | `app/crud.py` | SQL injection via f-string in `get_user_by_email` |
| 6 | L-02 | Logic | MEDIUM | `app/crud.py` | `divide_balance` divides without zero guard |
| 7 | L-04 | Logic | HIGH | `app/auth.py` | `decode_access_token` calls `jwt.decode` without try/except |

## Additional Detectable Issue — S-05

All 8 endpoints in `app/main.py` lack authentication dependencies. None include
`Depends(get_current_user)` or a `decode_access_token` call in their signature.
The Sentinel S-05 check flags every unprotected route handler.

This is intentional for the demo — S-05 is a **detection-only** rule (no auto-fix
is registered) because adding authentication to all routes is an architectural
decision that goes beyond a single-line patch. The `/health` and `/login`
endpoints are also legitimately public, which illustrates how the rule can
produce findings that require human review rather than automatic remediation.

## Details

### Bug 1 — L-01: Missing Balance Guard
**File:** `app/crud.py` — `transfer_funds()`  
**Problem:** Sender balance is decremented without first verifying it is ≥ amount. Allows negative balances.  
**Fix:** `if sender.balance < amount: return False`

### Bug 2 — S-03: Plain-Text Password
**File:** `app/crud.py` — `create_user()` and `login()`  
**Problem:** Password stored as `user_in.password` (no hashing). Compared with `==` operator.  
**Fix:** Hash on creation with `pwd_context.hash(password)`, verify with `pwd_context.verify()`

### Bug 3 — S-01: Hardcoded Secret
**File:** `app/auth.py`  
**Problem:** `SECRET_KEY = "super_secret_key_1234"` — secret committed to source code.  
**Fix:** `SECRET_KEY = os.environ["JWT_SECRET_KEY"]`

### Bug 4 — S-04: Weak JWT Configuration
**File:** `app/auth.py`  
**Problem:** Same as Bug 3 — weak, hardcoded HS256 key with no issuer/audience validation.  
**Fix:** Loaded from environment + add audience/issuer claims.

### Bug 5 — S-02: SQL Injection
**File:** `app/crud.py` — `get_user_by_email()`  
**Problem:** `text(f"SELECT * FROM users WHERE email = '{email}'")`  
An attacker can supply `' OR '1'='1` as the email to dump all users.  
**Fix:** `text("SELECT * FROM users WHERE email = :email")`, `{"email": email}`

### Bug 6 — L-02: Division by Zero
**File:** `app/crud.py` — `divide_balance()`  
**Problem:** `return user.balance / divisor` with no guard — crashes with `ZeroDivisionError` when `divisor=0`.  
**Fix:** `if divisor == 0: raise ValueError("divisor cannot be zero")`

### Bug 7 — L-04: Unhandled JWT Exception
**File:** `app/auth.py` — `decode_access_token()`  
**Problem:** `jwt.decode()` raises `jose.JWTError` on invalid/expired tokens; this is not caught.  
**Fix:** Wrap in `try/except jose.JWTError` and return `{}` or raise `HTTPException(401)`
