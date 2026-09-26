# Project Documentation Context (Non-Obvious Only)

- **`app/` contains intentional bugs** — the FastAPI app is a demo target, not production-quality code. All issues in `app/` are deliberate (documented with `BUG-N:` comments).
- **`test_baseline.py` tests assert broken behaviour** — tests like `test_transfer_allows_negative_balance_bug` are expected to pass against the buggy app. They are not broken tests; they document known bad state before `fix_agent` runs.
- **`test_regression.py` tests assert fixed behaviour** — these fail before fixes are applied. They are the canonical definition of "correct" post-fix behaviour.
- **README documents `tx_count` but code uses `transaction_count`** — `get_account_summary` in `app/crud.py` returns `{"balance": ..., "transaction_count": ...}`. The README field name is wrong (BUG-7 doc error).
- **`scan_directory` recurses everywhere** — documentation and examples always show `Path("app/")` as the argument; passing the repo root will produce false positives from `agents/` and `tests/`.
- **`ReviewReport.blocks_merge`** is `True` any time there is at least one CRITICAL or HIGH finding — the demo app always has `blocks_merge=True` in its unfixed state.
- **`agents/fix_agent.py` applies fixes by exact string match** — if you describe the fix mechanism, make clear it is not AST-based; it relies on the specific comment markers left in the buggy source files.
