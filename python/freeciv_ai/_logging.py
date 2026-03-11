"""
Unified logging for libfreeciv_ai.so output and freeciv-server subprocess output.

The .so writes its logs to fd 2 (C stderr) via cli_log_callback.
We redirect fd 2 to a pipe BEFORE dlopen(), then read it via an asyncio task
(no background threads).  Parsed "LEVEL: message" lines are routed through the
'freeciv_ai.lib' Python logger.  sys.stderr is restored to the real terminal.

Server subprocess stdout is forwarded the same way through 'freeciv_ai.server'.

All log writes go to sys.stdout via _PromptAwareHandler.  Because asyncio is
single-threaded, emit() can only run between 'await' yields — never while
input is being read — so a simple \\r\\033[2K + redraw is race-free.
"""

import asyncio
import fcntl
import os
import sys
import re
import logging
import readline

# Pattern: "3: some message"  (freeciv log level prefix)
_FC_LINE = re.compile(r"^(\d+): (.*)$")

# Freeciv log level → Python logging level
_FC_LEVELS = {
    0: logging.CRITICAL,  # LOG_FATAL
    1: logging.ERROR,     # LOG_ERROR / assertion failures
    2: logging.INFO,      # LOG_NORMAL
    3: logging.DEBUG,     # LOG_VERBOSE
    4: logging.DEBUG,     # LOG_DEBUG
}

_installed = False
_real_stderr = None       # file object wrapping the original terminal fd
_r_fd: int | None = None  # pipe read end — asyncio task reads from here
_handler: "logging.Handler | None" = None

# Current prompt — set by the REPL before/after each input wait.
_current_prompt: str = ""

# Optional TUI callback — when set, log messages are routed here instead of stdout.
_tui_log_callback = None  # type: ignore[assignment]


def set_tui_log_callback(fn) -> None:  # type: ignore[type-arg]
    """Route all log output to *fn(msg: str)* instead of stdout."""
    global _tui_log_callback
    _tui_log_callback = fn


def clear_tui_log_callback() -> None:
    """Restore normal stdout log output."""
    global _tui_log_callback
    _tui_log_callback = None


def set_prompt(prompt: str) -> None:
    """
    Tell the log handler what prompt is currently displayed.

    Call with the prompt string just before waiting for user input, and
    with ``""`` in a ``finally`` block after the input is received::

        from freeciv_ai._logging import set_prompt

        set_prompt("> ")
        try:
            line = await async_input("> ")
        finally:
            set_prompt("")
    """
    global _current_prompt
    _current_prompt = prompt


class _PromptAwareHandler(logging.StreamHandler):
    """
    A logging handler that cooperates with an asyncio-driven interactive prompt.

    Because asyncio is single-threaded, this handler is only called between
    'await' yields — never concurrently with input processing.  It:

    1. Issues \\r\\033[2K to move to the start of the current terminal line
       and erase it (clearing the prompt + any partial user input).
    2. Prints the formatted log message.
    3. Redraws the current prompt so the user sees where to type next.

    No lock is needed: single-threaded asyncio guarantees sequentiality.
    """

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            if _tui_log_callback is not None:
                _tui_log_callback(msg)
                return
            stream = self.stream
            stream.write(f"\r\033[2K{msg}\n")
            if _current_prompt:
                stream.write(_current_prompt + readline.get_line_buffer())
            stream.flush()
        except Exception:
            self.handleError(record)


class _FcFormatter(logging.Formatter):
    """Formats log records as  [SERVER] message  or  [CLIENT] message."""

    _TAGS = {
        "freeciv_ai.server": "SERVER",
        "freeciv_ai.lib":    "CLIENT",
    }

    def format(self, record: logging.LogRecord) -> str:
        tag = self._TAGS.get(record.name, record.name)
        return f"[{tag}] {record.getMessage()}"


def _make_handler(level: int) -> _PromptAwareHandler:
    h = _PromptAwareHandler(stream=sys.stdout)
    h.setFormatter(_FcFormatter())
    h.setLevel(level)
    return h


def _configure_logger(name: str, level: int, handler: logging.Handler) -> None:
    lg = logging.getLogger(name)
    lg.setLevel(level)
    lg.propagate = False
    lg.handlers.clear()
    lg.addHandler(handler)


def setup_logging(level: int = logging.INFO) -> None:
    """
    Configure clean, prefix-tagged logging for both freeciv streams.

    Output looks like::

        [SERVER] Loading rulesets.
        [SERVER] Accepting connections on port 5556.
        [CLIENT] STUB: tileset_type_set(1)

    Call once at the top of your script before any FreecivClient or
    FreecivServer operations::

        from freeciv_ai import setup_logging
        setup_logging()

    Optional *level* controls verbosity (default: ``logging.INFO``; pass
    ``logging.DEBUG`` to also see LOG_VERBOSE messages from the C library).
    """
    global _handler
    _ensure_so_capture()
    _handler = _make_handler(level)
    for name in ("freeciv_ai.server", "freeciv_ai.lib"):
        _configure_logger(name, level, _handler)

    # Also configure a plain handler on the root logger so that other
    # modules (e.g. freeciv_ai.torch.train) produce visible output.
    root = logging.getLogger()
    if not root.handlers:
        plain_handler = _PromptAwareHandler(stream=sys.stdout)
        plain_handler.setFormatter(
            logging.Formatter("%(levelname)s:%(name)s:%(message)s")
        )
        plain_handler.setLevel(level)
        root.setLevel(level)
        root.addHandler(plain_handler)


def _ensure_so_capture() -> None:
    """
    Redirect fd 2 (C stderr) to a pipe.  Idempotent.

    The pipe read end is stored in *_r_fd* for later consumption by the
    asyncio log task started in :func:`start_log_tasks`.

    Must be called before ``ffi.dlopen()`` so all .so output is captured.
    After this call ``sys.stderr`` points to the real terminal.
    """
    global _installed, _real_stderr, _handler, _r_fd

    if _installed:
        return

    # Save the real terminal before replacing fd 2.
    real_fd = os.dup(2)
    _real_stderr = open(real_fd, "w", buffering=1, closefd=True)
    sys.stderr = _real_stderr

    r_fd, w_fd = os.pipe()
    # Increase pipe buffer to 1 MB (Linux; F_SETPIPE_SZ capped at
    # /proc/sys/fs/pipe-max-size, default 1 MB for unprivileged users).
    _pipe_sz = getattr(fcntl, "F_SETPIPE_SZ", 1031)  # 1031 = F_SETPIPE_SZ on Linux
    try:
        fcntl.fcntl(r_fd, _pipe_sz, 1 << 20)
    except OSError:
        pass
    os.dup2(w_fd, 2)
    os.close(w_fd)
    # Non-blocking so a full pipe returns EAGAIN instead of deadlocking
    # the event loop while it's blocked inside a C call.
    fcntl.fcntl(2, fcntl.F_SETFL, fcntl.fcntl(2, fcntl.F_GETFL) | os.O_NONBLOCK)
    _r_fd = r_fd

    # Install a basic handler so messages emitted before the asyncio task
    # starts are not silently dropped.
    if _handler is None:
        _handler = _make_handler(logging.INFO)
    _configure_logger("freeciv_ai.lib", logging.INFO, _handler)

    _installed = True


_log_tasks: list[asyncio.Task] = []


async def start_log_tasks() -> None:
    """
    Start asyncio tasks that forward captured log streams to Python loggers.

    Call once from inside ``asyncio.run()`` (i.e. after the event loop has
    started).  Safe to call multiple times — subsequent calls are no-ops.
    Call :func:`stop_log_tasks` before the event loop exits to clean up.
    """
    global _r_fd
    if _r_fd is None:
        return

    r_fd = _r_fd
    _r_fd = None   # mark as consumed so re-entry is a no-op

    logger = logging.getLogger("freeciv_ai.lib")

    async def _read_pipe() -> None:
        loop = asyncio.get_running_loop()
        reader = asyncio.StreamReader()
        await loop.connect_read_pipe(
            lambda: asyncio.StreamReaderProtocol(reader),
            os.fdopen(r_fd, "rb", buffering=0),
        )
        srv_logger = logging.getLogger("freeciv_ai.server")
        try:
            async for data in reader:
                line = data.decode("utf-8", errors="replace").rstrip()
                if not line:
                    continue
                if line.startswith("S: "):
                    # Server command response forwarded from gui_real_output_window_append
                    srv_logger.info(line[3:])
                else:
                    m = _FC_LINE.match(line)
                    if m:
                        py_level = _FC_LEVELS.get(int(m.group(1)), logging.INFO)
                        logger.log(py_level, m.group(2))
                    else:
                        logger.info(line)
        except asyncio.CancelledError:
            pass

    task = asyncio.create_task(_read_pipe(), name="so-log")
    _log_tasks.append(task)


async def stop_log_tasks() -> None:
    """Cancel and await all log tasks started by :func:`start_log_tasks`."""
    for task in _log_tasks:
        task.cancel()
    for task in _log_tasks:
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass
    _log_tasks.clear()


async def forward_subprocess(
    proc,
    logger_name: str = "freeciv_ai.server",
    ready_event: asyncio.Event | None = None,
    ready_pattern: str | None = None,
) -> None:
    """
    Asyncio task: read *proc.stdout* line by line and route to *logger_name*.

    Optionally sets *ready_event* when *ready_pattern* appears in a line.
    Schedule as a task so it runs concurrently with the caller::

        asyncio.create_task(forward_subprocess(proc, ready_event=ev, ready_pattern="ready"))
        await ev.wait()
    """
    logger = logging.getLogger(logger_name)
    if not logger.handlers and _handler is not None:
        _configure_logger(logger_name, logging.INFO, _handler)

    try:
        async for data in proc.stdout:
            line = data.decode("utf-8", errors="replace").rstrip()
            if not line:
                continue
            m = _FC_LINE.match(line)
            if m:
                py_level = _FC_LEVELS.get(int(m.group(1)), logging.INFO)
                logger.log(py_level, m.group(2))
            else:
                logger.info(line)
            if ready_event and ready_pattern and ready_pattern in line:
                ready_event.set()
    except asyncio.CancelledError:
        pass
