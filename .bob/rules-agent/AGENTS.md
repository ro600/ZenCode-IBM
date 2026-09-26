# Project Coding Rules (Non-Obvious Only)

- **`Finding` is owned by `agents/sentinel.py`** — import from there in every agent. Never duplicate the dataclass.
- **Fix functions are brittle string replacements** — `agents/fix_agent.py` matches exact inline comment strings (`# BUG-1:`, `# BUG-2:`, etc.). Editing those comments breaks `apply_fixes` silently (`False` return, no error).
- **`S-01` and `S-04` share one fix** (`fix_s01_s04_hardcoded_secret`) — applying either rule_id calls the same function on `app/auth.py`. Don't write a separate fix for S-04.
- **Pass `app/` to `run_review`, not repo root** — `scan_directory` uses `rglob("*.py")` and will flag issues in `agents/` and `tests/` if given the root.
- **`client_no_raise` fixture required for 500-raising endpoints** — use it instead of `client` when testing BUG-6 (`/divide?divisor=0`) or any intentional crash; `client` re-raises server exceptions.
- **Pydantic v2 orm mode** — use `model_config = {"from_attributes": True}`, not `class Config: orm_mode = True`.
- **SQLAlchemy 2.x `DeclarativeBase`** — `app/database.py` uses `class Base(DeclarativeBase): pass`; do not switch to the legacy `declarative_base()` factory.
- **`db_engine` fixture is session-scoped** — schema is created once per pytest run. Adding a new model requires `Base.metadata.create_all` to pick it up; drop and recreate `test_prism.db` if schema gets stale.
- **`test_baseline.py` intentionally asserts broken behaviour** — e.g. `assert resp.status_code == 200` on an overdraft transfer. Do not fix those assertions; they document pre-fix state.
- **`get_account_summary` returns a plain `dict`, not a JSON response** — the docstring lies (BUG-7). The actual field is `transaction_count`, not `tx_count` as the README says.
