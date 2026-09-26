"""
Fix Workflow Agent
==================
Applies approved security and logic fixes to the codebase.

Each fix is keyed by rule_id. Fixes are pattern-based replacements that
correct the intentional bugs inserted for the demo.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Callable


# ---------------------------------------------------------------------------
# Individual fix functions
# ---------------------------------------------------------------------------

def fix_s01_s04_hardcoded_secret(path: Path) -> bool:
    """S-01 / S-04: Replace hardcoded SECRET_KEY with os.environ lookup."""
    text = path.read_text(encoding="utf-8")
    if 'SECRET_KEY = "super_secret_key_1234"' not in text:
        return False

    patched = text.replace(
        'SECRET_KEY = "super_secret_key_1234"   # noqa: S105',
        'import os\n\nSECRET_KEY = os.environ.get("JWT_SECRET_KEY", "changeme-in-production")  # noqa: S105',
    )
    path.write_text(patched, encoding="utf-8")
    return True


def fix_s02_sql_injection(path: Path) -> bool:
    """S-02: Replace f-string SQL with parameterised query."""
    text = path.read_text(encoding="utf-8")
    old = "    query = text(f\"SELECT * FROM users WHERE email = '{email}'\")  # noqa: S608\n    result = db.execute(query).fetchone()"
    new = "    query = text(\"SELECT * FROM users WHERE email = :email\")\n    result = db.execute(query, {\"email\": email}).fetchone()"
    if old not in text:
        return False
    path.write_text(text.replace(old, new), encoding="utf-8")
    return True


def fix_s03_plain_text_password(path: Path) -> bool:
    """S-03: Replace plain-text password storage and comparison with passlib."""
    text = path.read_text(encoding="utf-8")

    # Add passlib import if missing
    if "from passlib.context import CryptContext" not in text:
        text = text.replace(
            "from app.auth import create_access_token",
            "from passlib.context import CryptContext\nfrom app.auth import create_access_token\n\npwd_context = CryptContext(schemes=[\"bcrypt\"], deprecated=\"auto\")",
        )

    # Fix storage
    text = text.replace(
        "        password=user_in.password,   # BUG-2: no hashing",
        "        password=pwd_context.hash(user_in.password),",
    )
    # Fix comparison
    text = text.replace(
        "    if user.password != password:   # BUG-2: plain-text compare",
        "    if not pwd_context.verify(password, user.password):",
    )
    path.write_text(text, encoding="utf-8")
    return True


def fix_l01_balance_guard(path: Path) -> bool:
    """L-01: Add balance check before debit in transfer_funds."""
    text = path.read_text(encoding="utf-8")
    old = "    # BUG-1: missing:  if sender.balance < amount: return False\n    sender.balance -= amount"
    new = "    if sender.balance < amount:\n        return False\n    sender.balance -= amount"
    if old not in text:
        return False
    path.write_text(text.replace(old, new), encoding="utf-8")
    return True


def fix_l02_division_zero(path: Path) -> bool:
    """L-02: Add zero-division guard in divide_balance."""
    text = path.read_text(encoding="utf-8")
    old = "    return user.balance / divisor   # BUG-6: ZeroDivisionError when divisor == 0"
    new = "    if divisor == 0:\n        raise ValueError(\"divisor cannot be zero\")\n    return user.balance / divisor"
    if old not in text:
        return False
    path.write_text(text.replace(old, new), encoding="utf-8")
    return True


def fix_l04_unhandled_jwt(path: Path) -> bool:
    """L-04: Wrap jwt.decode in try/except."""
    text = path.read_text(encoding="utf-8")
    old = "    # BUG-4: no verification of audience/issuer, exception not handled\n    return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])"
    new = (
        "    try:\n"
        "        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])\n"
        "    except Exception:\n"
        "        return {}"
    )
    if old not in text:
        return False
    path.write_text(text.replace(old, new), encoding="utf-8")
    return True


# ---------------------------------------------------------------------------
# Fix registry
# ---------------------------------------------------------------------------

_FIXES: dict[str, tuple[str, Callable[[Path], bool]]] = {
    "S-01": ("app/auth.py", fix_s01_s04_hardcoded_secret),
    "S-02": ("app/crud.py", fix_s02_sql_injection),
    "S-03": ("app/crud.py", fix_s03_plain_text_password),
    "S-04": ("app/auth.py", fix_s01_s04_hardcoded_secret),
    "L-01": ("app/crud.py", fix_l01_balance_guard),
    "L-02": ("app/crud.py", fix_l02_division_zero),
    "L-04": ("app/auth.py", fix_l04_unhandled_jwt),
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def apply_fixes(rule_ids: list[str], repo_root: Path) -> dict[str, bool]:
    """Apply fixes for the given rule IDs. Returns {rule_id: success}."""
    results: dict[str, bool] = {}
    applied_files: set[str] = set()

    for rule_id in rule_ids:
        if rule_id not in _FIXES:
            results[rule_id] = False
            continue
        rel_path, fix_fn = _FIXES[rule_id]
        target = repo_root / rel_path
        # Avoid double-applying fixes that touch the same file
        file_key = f"{rule_id}:{rel_path}"
        if file_key in applied_files:
            results[rule_id] = True  # already applied by companion rule
            continue
        applied_files.add(file_key)
        results[rule_id] = fix_fn(target)

    return results


def apply_all_fixes(repo_root: Path) -> dict[str, bool]:
    """Apply every registered fix."""
    return apply_fixes(list(_FIXES.keys()), repo_root)
