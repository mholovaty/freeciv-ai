import asyncio
import functools
import socket


def timeout(seconds: float):
    """
    Decorator that cancels an async test after *seconds*.

    Uses asyncio.timeout() so CancelledError propagates normally —
    all finally blocks in the test body run before the timeout is reported.

    Usage::

        @timeout(30)
        async def test_something():
            ...
    """
    def decorator(fn):
        @functools.wraps(fn)
        async def wrapper(*args, **kwargs):
            async with asyncio.timeout(seconds):
                return await fn(*args, **kwargs)
        return wrapper
    return decorator


def get_free_port() -> int:
    """Return an available TCP port on 127.0.0.1."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]
