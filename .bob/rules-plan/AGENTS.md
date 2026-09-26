# Project Architecture Rules (Non-Obvious Only)

- **Agents are stateless scanners, not persistent services** — each agent re-reads files on every `scan_directory` call. There is no caching layer or in-process state between runs.
- **Fix agent is destructive by design** — `apply_fixes` writes directly to source files in-place. There is no dry-run mode or rollback. Fixes must be idempotent: if the exact old string is absent (already fixed), `fix_fn` returns `False` and writes nothing.
- **Deduplication key is `(file, line, rule_id)`** — aggregator deduplicates at that granularity. Two agents flagging the same line with different rule IDs will both appear. Agents flagging the same rule on the same line are collapsed to one.
- **`S-01` and `S-04` intentionally map to the same fix** — architectural decision to avoid double-patching `app/auth.py`. The `_FIXES` registry guards with `file_key = f"{rule_id}:{rel_path}"` to skip the second application.
- **`test_prism.db` is a file-system artifact** — it persists between test runs and is not cleaned up by pytest. A stale schema (after a model change) requires manual deletion; no migration tooling exists.
- **The app has no authentication middleware** — endpoints like `/transfer` and `/users/{id}/summary` have no bearer-token check. The `/login` endpoint issues JWTs but nothing validates them on protected routes (S-05 is an open rule, not yet enforced by a fix).
- **`scan_directory` coupling** — both Sentinel and Logic independently call `path.rglob("*.py")` on the same target. Adding a third agent follows the same pattern; the Aggregator simply calls it and merges findings. No agent registry or plugin system exists.
- **Fix coverage gap** — `S-05` (unauthenticated endpoint) and `L-03` (implicit None return) have detection rules but **no corresponding fix function** in `agents/fix_agent.py`. Planning to cover them requires adding both a fix function and a `_FIXES` entry.
