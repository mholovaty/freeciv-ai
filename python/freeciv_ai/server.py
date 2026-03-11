"""
FreecivServer — manages a local freeciv-server subprocess via asyncio.
"""

import asyncio
import os
import tempfile

from ._logging import forward_subprocess


class FreecivServer:
    """
    Manages a local ``freeciv-server`` subprocess.

    On :meth:`start`:

    * writes a temporary server script that grants every new connection
      ``hack`` access level automatically (``/cmdlevel hack new``);
    * launches ``freeciv-server`` with that script via asyncio;
    * waits until the server reports it is accepting connections.

    The server's stdout is forwarded to the ``freeciv_ai.server`` Python
    logger via an asyncio task (no threads).
    """

    DEFAULT_PORT = 5556

    def __init__(self) -> None:
        self._proc: asyncio.subprocess.Process | None = None
        self._port: int | None = None
        self._script_path: str | None = None

    async def __aenter__(self) -> "FreecivServer":
        return self

    async def __aexit__(self, *_) -> None:
        await self.stop()

    @property
    def port(self) -> int | None:
        return self._port

    @property
    def running(self) -> bool:
        return self._proc is not None and self._proc.returncode is None

    async def start(
        self,
        port: int = DEFAULT_PORT,
        *,
        maxplayers: int = 1,
        aifill: int = 0,
        endturn: int = 0,
        timeout_secs: int = 0,
        extra_cmds: list[str] | None = None,
        saves_dir: str | None = None,
        wait_timeout: float = 15.0,
    ) -> "FreecivServer":
        """
        Launch the server and wait until it is ready to accept connections.

        Parameters
        ----------
        port:
            TCP port for the server to listen on.
        maxplayers:
            Maximum number of human players.
        aifill:
            Number of AI fill players (0 = only the Python client plays).
        endturn:
            Turn on which the game ends automatically (0 = no limit).
        timeout_secs:
            Per-turn time limit in seconds (0 = wait for player).
        extra_cmds:
            Additional server commands run at startup (``/`` prefix optional).
        saves_dir:
            Directory passed to ``freeciv-server --saves``.  When *None* the
            server uses its default save location.
        wait_timeout:
            Seconds to wait for the server to become ready.

        Returns self for chaining / use as async context manager.
        """
        cmds = [
            "/cmdlevel hack new",
            f"/set aifill {aifill}",
            f"/set maxplayers {maxplayers}",
        ]
        if endturn > 0:
            cmds.append(f"/set endturn {endturn}")
        if timeout_secs > 0:
            cmds.append(f"/set timeout {timeout_secs}")
        if extra_cmds is not None:
            for c in extra_cmds:
                cmds.append(c if c.startswith("/") else f"/{c}")

        fd, path = tempfile.mkstemp(suffix=".serv", prefix="freeciv_ai_")
        with os.fdopen(fd, "w") as f:
            f.write("\n".join(cmds) + "\n")
        self._script_path = path
        self._port = port

        self._proc = await asyncio.create_subprocess_exec(
            "freeciv-server",
            "-p",
            str(port),
            "-r",
            path,
            "-q",
            "600",
            *(["-s", saves_dir] if saves_dir is not None else []),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )

        ready_event = asyncio.Event()
        ready_pattern = f"accepting new client connections on port {port}"
        asyncio.create_task(
            forward_subprocess(
                self._proc,
                ready_event=ready_event,
                ready_pattern=ready_pattern,
            ),
            name="server-log",
        )

        try:
            await asyncio.wait_for(ready_event.wait(), timeout=wait_timeout)
        except asyncio.TimeoutError:
            await self.stop(force=True)
            raise TimeoutError(
                f"freeciv-server did not become ready within {wait_timeout}s"
            )

        return self

    async def stop(self, force: bool = False) -> None:
        """
        Shut down the server: send ``/quit`` and wait up to 5 s for a clean
        exit, then kill if necessary.
        """
        if self._proc is None:
            return
        if not force and self._proc.returncode is None:
            try:
                self._proc.stdin.write(b"/quit\n")
                await self._proc.stdin.drain()
                await asyncio.wait_for(self._proc.wait(), timeout=5.0)
            except Exception:
                pass
        if self._proc.returncode is None:
            self._proc.kill()
            await self._proc.wait()
        self._proc = None
        self._cleanup_script()

    def force_kill(self) -> None:
        """
        Synchronously kill the server process immediately (no graceful quit).

        Safe to call from a ``finally`` block or signal handler where
        ``await`` is not available.
        """
        if self._proc is not None and self._proc.returncode is None:
            self._proc.kill()
        self._cleanup_script()
        self._proc = None

    async def send(self, cmd: str) -> None:
        """Send a command to the server's stdin console."""
        if self._proc and self._proc.returncode is None:
            line = cmd if cmd.startswith("/") else f"/{cmd}"
            self._proc.stdin.write((line + "\n").encode())
            await self._proc.stdin.drain()

    def _cleanup_script(self) -> None:
        if self._script_path and os.path.exists(self._script_path):
            try:
                os.unlink(self._script_path)
            except OSError:
                pass
        self._script_path = None
