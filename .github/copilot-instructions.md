# Python style
- `str | None` not `Optional[str]`
- `pathlib.Path` not `os.path`
- All imports at file top
- Comments only where semantics are non-obvious; none for obvious code

# Error handling
- Fail fast — no silent exception suppression

# Async
- Background polling starts in `connect()`, stops in `stop()` — never exposed to callers
- Async timeouts via `asyncio.timeout()` (Python ≥ 3.11)
- `requires-python = ">=3.11"`

# Tests
- `pytest-asyncio` with `asyncio_mode = "auto"` — `async def test_*` runs directly
- Shared test utilities (e.g. `timeout`, `get_free_port`) live in `tests/conftest.py`
- Never overwrite `conftest.py` contents without reading it first

# Responses
- Concise; no lengthy explanations of what was done or why
- No filler commentary in code
