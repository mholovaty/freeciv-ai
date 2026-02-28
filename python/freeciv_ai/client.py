"""
High-level Python wrapper around the freeciv_ai CFFI bindings.

Python drives the network event loop via asyncio + freeciv_ai_input().
freeciv_ai_connect() runs freeciv's client_main() in a ucontext coroutine
and returns once the connection is established (single-threaded, no threads).

Usage::

    import asyncio
    from freeciv_ai import FreecivClient, ClientState, setup_logging
    from freeciv_ai._logging import start_log_tasks

    async def main():
        setup_logging()
        await start_log_tasks()

        with FreecivClient() as client:
            client.init()
            client.connect(host="localhost", port=5556, username="my-ai")

            while client.in_game:
                await client.poll(timeout=0.1)
                if client.can_act:
                    units = client.get_units()
                    client.end_turn()

    asyncio.run(main())
"""

import asyncio
from enum import IntEnum

from ._lib import ffi, load_lib, find_data_path


class ClientState(IntEnum):
    """Mirrors freeciv's enum client_states."""
    INITIAL      = 0   # C_S_INITIAL      — client boot / just started
    DISCONNECTED = 1   # C_S_DISCONNECTED — not connected (also used for errors)
    PREPARING    = 2   # C_S_PREPARING    — connected, in pre-game lobby
    RUNNING      = 3   # C_S_RUNNING      — game in progress


class FreecivClient:
    """
    Python client for a Freeciv server.

    freeciv_ai_connect() runs the freeciv client_main() initialisation in a
    POSIX coroutine and returns once connected.  Python then drives the
    network event loop through :meth:`poll`.
    """

    def __init__(self, so_path: str = None):
        self._lib, self._so_path = load_lib(so_path)
        self._initialized = False
        self._polling = False  # guard: only one poll() active at a time

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def init(self, data_path: str = None) -> "FreecivClient":
        """
        Initialise the freeciv subsystems.

        Must be called before :meth:`connect`.  ``data_path`` is the path to
        the ``freeciv/data`` directory.  When omitted, the path is inferred
        from the location of ``libfreeciv_ai.so`` in the build tree.
        """
        if data_path is None:
            data_path = find_data_path(self._so_path)
        dp = data_path.encode() if data_path else ffi.NULL
        self._lib.freeciv_ai_init(dp)
        self._initialized = True
        return self

    def connect(self, host: str = "localhost", port: int = 5556,
                username: str = "ai-player") -> "FreecivClient":
        """
        Connect to a Freeciv server.

        Runs freeciv's client_main() in a coroutine until the connection is
        established (or fails).  Returns once the pre-game lobby is reached.

        Raises :exc:`ConnectionError` if the server cannot be reached.
        """
        if not self._initialized:
            self.init()

        ret = self._lib.freeciv_ai_connect(
            host.encode(), port, username.encode()
        )
        if ret != 0:
            raise ConnectionError(f"Failed to connect to {host}:{port}")
        return self

    def stop(self) -> None:
        """Disconnect from the server and clean up."""
        self._lib.freeciv_ai_stop()

    def __enter__(self) -> "FreecivClient":
        return self

    def __exit__(self, *_) -> None:
        self.stop()

    # ------------------------------------------------------------------
    # State queries
    # ------------------------------------------------------------------

    @property
    def state(self) -> ClientState:
        """Current :class:`ClientState`."""
        return ClientState(self._lib.freeciv_ai_get_client_state())

    @property
    def in_game(self) -> bool:
        """``True`` while the game is running (``ClientState.RUNNING``)."""
        return self.state == ClientState.RUNNING

    @property
    def can_act(self) -> bool:
        """``True`` when the local player can issue orders this turn."""
        return bool(self._lib.freeciv_ai_can_act())

    @property
    def turn(self) -> int:
        """Current game turn number."""
        return self._lib.freeciv_ai_get_turn()

    # ------------------------------------------------------------------
    # Unit queries
    # ------------------------------------------------------------------

    def get_units(self, max_units: int = 1024) -> list[dict]:
        """
        Return a list of dicts describing every unit owned by the local player.

        Each dict has keys: ``id``, ``x``, ``y``, ``hp``, ``hp_max``,
        ``moves_left``, ``moves_max``, ``type``.
        """
        buf = ffi.new("freeciv_unit_t[]", max_units)
        n = self._lib.freeciv_ai_get_units(buf, max_units)
        return [
            {
                "id":         buf[i].id,
                "x":          buf[i].x,
                "y":          buf[i].y,
                "hp":         buf[i].hp,
                "hp_max":     buf[i].hp_max,
                "moves_left": buf[i].moves_left,
                "moves_max":  buf[i].moves_max,
                "type":       ffi.string(buf[i].type_name).decode("utf-8",
                                                                   errors="replace"),
            }
            for i in range(n)
        ]

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    def move_unit(self, unit_id: int, direction: int) -> None:
        """
        Move a unit one step in a compass direction.

        ``direction``: 0=N 1=NE 2=E 3=SE 4=S 5=SW 6=W 7=NW
        (matches freeciv's ``enum direction8``).
        """
        self._lib.freeciv_ai_move_unit(unit_id, direction)

    def end_turn(self) -> None:
        """Send a turn-done packet to the server."""
        self._lib.freeciv_ai_end_turn()

    # ------------------------------------------------------------------
    # Server control (chat / commands)
    # ------------------------------------------------------------------

    @property
    def has_hack(self) -> bool:
        """
        ``True`` if this client holds 'hack' access level on the server.

        Hack level grants full server-console control: ``/set``, ``/start``,
        ``/quit``, ``/save``, etc.  It is negotiated automatically when
        client and server run as the same OS user on the same machine
        (filesystem challenge).  For a remote server the admin must grant it
        with ``/cmdlevel hack <username>`` from the server console.
        """
        return bool(self._lib.freeciv_ai_has_hack())

    def send_chat(self, message: str) -> int:
        """
        Send a raw chat message or server command.

        Messages that start with ``/`` are treated as server commands, e.g.::

            client.send_chat("/set timeout 30")
            client.send_chat("/start")
            client.send_chat("/save my_game")

        Normal messages (no ``/`` prefix) appear in the in-game chat.
        Returns the number of bytes sent, or -1 on error.
        """
        return self._lib.freeciv_ai_send_chat(message.encode())

    def send_command(self, cmd: str) -> int:
        """
        Send a server command.  A ``/`` prefix is added automatically if
        *cmd* does not already start with one.

        Example::

            client.send_command("set timeout 30")   # → /set timeout 30
            client.send_command("/start")            # → /start
        """
        if not cmd.startswith("/"):
            cmd = "/" + cmd
        return self.send_chat(cmd)

    def start_game(self) -> None:
        """
        Send ``/start`` to the server to begin the game.

        Requires hack access level.  Call :meth:`wait_for_hack` first.
        """
        self.send_command("start")

    # ------------------------------------------------------------------
    # Network event loop (asyncio-driven)
    # ------------------------------------------------------------------

    async def poll(self, timeout: float = 0.05) -> bool:
        """
        Drive the network event loop for up to *timeout* seconds.

        Registers the server socket with asyncio's event loop and awaits
        readability, then calls ``freeciv_ai_input`` to process the packet.
        Returns ``True`` if the connection is still alive, ``False`` if
        disconnected.

        Call this regularly in your main loop to process incoming packets::

            while client.in_game:
                await client.poll()
                if client.can_act:
                    ...
        """
        fd = self._lib.freeciv_ai_get_socket()
        if fd < 0:
            return self.state != ClientState.DISCONNECTED

        # Only one poll() may be active at a time (single-threaded asyncio,
        # but multiple tasks may call poll() concurrently).
        if self._polling:
            await asyncio.sleep(0)
            return self.state != ClientState.DISCONNECTED

        self._polling = True
        loop = asyncio.get_running_loop()
        ev = asyncio.Event()

        def _readable() -> None:
            loop.remove_reader(fd)
            self._polling = False
            ev.set()

        loop.add_reader(fd, _readable)
        try:
            await asyncio.wait_for(ev.wait(), timeout=timeout)
            self._lib.freeciv_ai_input(fd)
        except asyncio.TimeoutError:
            loop.remove_reader(fd)
            self._polling = False

        return self.state != ClientState.DISCONNECTED

    async def wait_for_turn(self) -> None:
        """Await until :attr:`can_act` is ``True``, pumping the event loop."""
        while not self.can_act:
            if not await self.poll(timeout=0.05):
                raise ConnectionError("Disconnected from server")

    async def wait_for_hack(self, timeout: float = 5.0) -> bool:
        """
        Poll until the server grants hack access level, or *timeout* expires.

        Returns ``True`` if hack was obtained, ``False`` on timeout.
        Hack is negotiated automatically on localhost via a filesystem
        challenge; a few poll cycles are needed to receive the reply packet.
        """
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while loop.time() < deadline:
            await self.poll(timeout=0.1)
            if self.has_hack:
                return True
        return False

    async def start_server(
        self,
        port: int = 5556,
        *,
        maxplayers: int = 1,
        aifill: int = 0,
        endturn: int = 0,
        timeout_secs: int = 0,
        extra_cmds: list[str] = (),
        username: str = "ai-player",
        auto_start: bool = True,
    ) -> "FreecivServer":
        """
        Start a local ``freeciv-server``, connect to it, and optionally start
        the game — all in one call.

        The server is configured with ``/cmdlevel hack new`` so hack level is
        granted automatically.  When *auto_start* is ``True`` (the default),
        ``/start`` is sent after hack is confirmed.

        Returns the :class:`FreecivServer` instance (async context manager)::

            async with await client.start_server(port=5556) as server:
                while client.in_game:
                    await client.poll()
                    if client.can_act:
                        client.end_turn()
        """
        import logging
        from .server import FreecivServer

        server = await FreecivServer().start(
            port=port,
            maxplayers=maxplayers,
            aifill=aifill,
            endturn=endturn,
            timeout_secs=timeout_secs,
            extra_cmds=extra_cmds,
        )

        if not self._initialized:
            self.init()
        self.connect(host="localhost", port=port, username=username)

        if auto_start:
            if not await self.wait_for_hack():
                logging.getLogger("freeciv_ai.lib").warning(
                    "Could not obtain hack level — /start may fail"
                )
            self.start_game()

        return server
