"""
High-level Python wrapper around the freeciv_ai CFFI bindings.

"""

import asyncio
import logging
import select as _select
from enum import IntEnum

from ._lib import ffi, load_lib, find_data_path


_logger = logging.getLogger(__name__)


class ClientState(IntEnum):
    """Mirrors freeciv's enum client_states."""

    INITIAL = 0       # C_S_INITIAL      — client boot / just started
    DISCONNECTED = 1  # C_S_DISCONNECTED — not connected (also used for errors)
    PREPARING = 2     # C_S_PREPARING    — connected, in pre-game lobby
    RUNNING = 3       # C_S_RUNNING      — game in progress
    OVER = 4          # C_S_OVER         — game over, score screen


class FreecivClient:
    """
    Python client for a Freeciv server.

    freeciv_ai_connect() runs the freeciv client_main() initialisation in a
    POSIX coroutine and returns once connected.  Python then drives the
    network event loop through :meth:`poll`.
    """

    def __init__(self, so_path: str | None = None, data_path: str | None = None):
        self._lib, self._so_path = load_lib(so_path)
        self._polling = False  # guard: only one poll() active at a time
        self._poll_task: asyncio.Task | None = None
        if data_path is None:
            data_path = find_data_path(self._so_path)
        dp = data_path.encode() if data_path else ffi.NULL
        self._lib.freeciv_ai_init(dp)

    def connect(
        self, host: str = "localhost", port: int = 5556, username: str = "ai-player"
    ) -> "FreecivClient":
        """
        Connect to a Freeciv server.

        Runs freeciv's client_main() in a coroutine until the connection is
        established (or fails).  Returns once the pre-game lobby is reached.

        Raises :exc:`ConnectionError` if the server cannot be reached.
        """
        ret = self._lib.freeciv_ai_connect(host.encode(), port, username.encode())
        if ret != 0:
            raise ConnectionError(f"Failed to connect to {host}:{port}")
        loop = asyncio.get_running_loop()
        if self._poll_task is None:
            self._poll_task = loop.create_task(self._poll_loop(), name="freeciv-poll")
        return self

    def stop(self) -> None:
        """Disconnect from the server and clean up."""
        if self._poll_task is not None:
            self._poll_task.cancel()
            self._poll_task = None
        self._lib.freeciv_ai_stop()

    async def reconnect(
        self, host: str = "localhost", port: int = 5556, username: str = "ai-player"
    ) -> None:
        """
        Disconnect from the current server and immediately reconnect to *host*:*port*.

        Reuses the existing C coroutine — no ``client_main()`` re-run.
        Safe to call between episodes to reset game state without restarting
        the library.  Raises :exc:`ConnectionError` on failure.
        """
        if self._poll_task is not None:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except (asyncio.CancelledError, Exception):
                pass
            self._poll_task = None
        self._polling = False  # reset in case task was cancelled mid-poll
        ret = self._lib.freeciv_ai_reconnect(host.encode(), port, username.encode())
        if ret != 0:
            raise ConnectionError(f"Failed to reconnect to {host}:{port}")
        loop = asyncio.get_running_loop()
        self._poll_task = loop.create_task(self._poll_loop(), name="freeciv-poll")

    def __enter__(self) -> "FreecivClient":
        return self

    def __exit__(self, *_) -> None:
        self.stop()

    async def poll(self, timeout: float = 0.05) -> bool:
        """
        Drive the network event loop for up to *timeout* seconds.

        Uses select() instead of asyncio.add_reader to avoid epoll fd-reuse
        bugs when the same fd number is allocated for a new socket after
        reconnect.
        """
        fd = self._lib.freeciv_ai_get_socket()
        if fd < 0:
            await asyncio.sleep(timeout)
            return self.state != ClientState.DISCONNECTED

        if self._polling:
            await asyncio.sleep(0.01)
            return self.state != ClientState.DISCONNECTED

        self._polling = True
        try:
            loop = asyncio.get_running_loop()
            readable, _, _ = await loop.run_in_executor(
                None, lambda: _select.select([fd], [], [], timeout)
            )
            if readable:
                self._lib.freeciv_ai_input(fd)
        except BaseException:
            raise
        finally:
            self._polling = False

        return self.state != ClientState.DISCONNECTED

    async def _poll_loop(self, interval: float = 0.1) -> None:
        while True:
            await self.poll(timeout=interval)

    async def _stop_polling(self) -> None:
        if self._poll_task is None:
            return
        self._poll_task.cancel()
        try:
            await self._poll_task
        except asyncio.CancelledError:
            pass
        self._poll_task = None

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
                "id": buf[i].id,
                "x": buf[i].x,
                "y": buf[i].y,
                "hp": buf[i].hp,
                "hp_max": buf[i].hp_max,
                "moves_left": buf[i].moves_left,
                "moves_max": buf[i].moves_max,
                "type": ffi.string(buf[i].type_name).decode("utf-8", errors="replace"),
            }
            for i in range(n)
        ]

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

    @property
    def map_width(self) -> int:
        """Map width in tiles."""
        return self._lib.freeciv_ai_map_width()

    @property
    def map_height(self) -> int:
        """Map height in tiles."""
        return self._lib.freeciv_ai_map_height()

    @property
    def map_topology_id(self) -> int:
        """Topology bitmask: TF_ISO=1, TF_HEX=2."""
        return self._lib.freeciv_ai_map_topology_id()

    @property
    def map_wrap_id(self) -> int:
        """Wrap bitmask: WRAP_X=1, WRAP_Y=2."""
        return self._lib.freeciv_ai_map_wrap_id()

    def tile_index(self, x: int, y: int) -> int:
        """
        Convert (x, y) coordinates to a tile index.

        The tile index is used as ``target_id`` for tile-targeted actions
        such as ``ACTION_UNIT_MOVE``, ``ACTION_FORTIFY``,
        ``ACTION_FOUND_CITY``, etc.  Returns -1 for out-of-bounds coords.
        """
        return self._lib.freeciv_ai_tile_index(x, y)

    def get_map(self, max_tiles: int = 131072) -> list[dict]:
        """
        Return a list of dicts describing every map tile.

        Each dict has keys: ``x``, ``y``, ``index``, ``known``,
        ``terrain``, ``owner``, ``city_id``, ``city_name``,
        ``n_units``, ``extras``.

        ``known`` is 0 (unknown), 1 (seen before but fogged), or
        2 (currently visible).  ``terrain`` and city fields are empty /
        -1 for unknown tiles.
        """
        buf = ffi.new("freeciv_tile_t[]", max_tiles)
        n = self._lib.freeciv_ai_get_tiles(buf, max_tiles)
        result = []
        for i in range(n):
            t = buf[i]
            result.append(
                {
                    "x": t.x,
                    "y": t.y,
                    "index": t.index,
                    "known": t.known,
                    "terrain": ffi.string(t.terrain).decode("utf-8", errors="replace"),
                    "owner": t.owner,
                    "city_id": t.city_id,
                    "city_name": ffi.string(t.city_name).decode(
                        "utf-8", errors="replace"
                    ),
                    "n_units": t.n_units,
                    "extras": t.extras,
                }
            )
        return result

    def get_tile_units(self, x: int, y: int, max_units: int = 64) -> list[dict]:
        """
        Return a list of dicts for every unit on tile (x, y).

        Same fields as :meth:`get_units`.
        """
        buf = ffi.new("freeciv_unit_t[]", max_units)
        n = self._lib.freeciv_ai_get_tile_units(x, y, buf, max_units)
        return [
            {
                "id": buf[i].id,
                "x": buf[i].x,
                "y": buf[i].y,
                "hp": buf[i].hp,
                "hp_max": buf[i].hp_max,
                "moves_left": buf[i].moves_left,
                "moves_max": buf[i].moves_max,
                "type": ffi.string(buf[i].type_name).decode("utf-8", errors="replace"),
            }
            for i in range(n)
        ]

    def get_cities(self, max_cities: int = 1024) -> list[dict]:
        """
        Return a list of dicts describing every city owned by the local player.

        Each dict has keys: ``id``, ``name``, ``x``, ``y``, ``owner``,
        ``size``, ``food_surplus``, ``prod_surplus``, ``trade``, ``science``,
        ``food_stock``, ``granary_size``, ``shield_stock``, ``prod_cost``, ``prod_name``.
        """
        buf = ffi.new("freeciv_city_t[]", max_cities)
        n = self._lib.freeciv_ai_get_cities(buf, max_cities)
        return [
            {
                "id": buf[i].id,
                "name": ffi.string(buf[i].name).decode("utf-8", errors="replace"),
                "x": buf[i].x,
                "y": buf[i].y,
                "owner": buf[i].owner,
                "size": buf[i].size,
                "food_surplus": buf[i].food_surplus,
                "prod_surplus": buf[i].prod_surplus,
                "trade": buf[i].trade,
                "science": buf[i].science,
                "food_stock": buf[i].food_stock,
                "granary_size": buf[i].granary_size,
                "shield_stock": buf[i].shield_stock,
                "prod_cost": buf[i].prod_cost,
                "prod_name": ffi.string(buf[i].prod_name).decode("utf-8", errors="replace"),
            }
            for i in range(n)
        ]

    def can_do_action(self, unit_id: int, action_id: int, target_id: int = 0) -> int:
        """
        Check if *unit_id* can perform *action_id* against *target_id*.

        *target_id* meaning depends on the action:

        * Tile-targeted actions (UNIT_MOVE, FORTIFY, FOUND_CITY, …):
          pass ``tile_index(x, y)``
        * Unit-targeted actions (ATTACK, …): pass the target unit id
        * City-targeted actions: pass the target city id
        * Self-targeted actions: *target_id* is ignored

        Returns the minimum success probability (0–200, where 200 is
        certain), or -1 if the action is impossible / invalid.
        """
        return self._lib.freeciv_ai_can_do_action(unit_id, action_id, target_id)

    def request_city_name_suggestion(self, unit_id: int) -> None:
        """Ask the server for a nation-appropriate city name for *unit_id*.

        The server replies with PACKET_CITY_NAME_SUGGESTION_INFO.  The stub
        GUI handler (popup_newcity_dialog) receives the reply and immediately
        founds the city with the suggested name.  Call poll() after this to
        process the round-trip.
        """
        self._lib.freeciv_ai_request_city_name_suggestion(unit_id)

    def do_action(
        self,
        unit_id: int,
        action_id: int,
        target_id: int,
        sub_tgt: int = 0,
        name: str = "",
    ) -> None:
        """
        Ask the server to perform *action_id* with unit *unit_id*.

        *target_id* semantics are the same as for :meth:`can_do_action`.

        *sub_tgt*: sub-target (tech id, building id, …) — 0 for most
        actions.

        *name*: city or unit name for actions that require one (e.g.
        ``ACTION_FOUND_CITY``); leave empty otherwise.

        Example — move unit 42 to the tile one square north-east::

            idx = client.tile_index(x + 1, y - 1)
            client.do_action(42, Actions.UNIT_MOVE, idx)

        Example — attack unit 99::

            client.do_action(42, Actions.ATTACK, 99)
        """
        self._lib.freeciv_ai_do_action(
            unit_id, action_id, target_id, sub_tgt, name.encode()
        )

    def get_action_decision(self) -> dict | None:
        """
        Return the pending action decision (if any) as a dict, else None.

        The dict has keys:
          ``actor_id``  — unit that needs to act
          ``choices``   — list of dicts with ``action_id``, ``name``,
                          ``target_id``, ``min_prob``
        """
        buf = ffi.new("freeciv_action_decision_t *")
        if not self._lib.freeciv_ai_get_action_decision(buf):
            return None
        choices = []
        for i in range(buf.n_choices):
            c = buf.choices[i]
            choices.append(
                {
                    "action_id": c.action_id,
                    "name": ffi.string(c.name).decode("utf-8", errors="replace"),
                    "target_id": c.target_id,
                    "min_prob": c.min_prob,
                }
            )
        return {"actor_id": buf.actor_id, "choices": choices}

    def resolve_action_decision(
        self, actor_id: int, action_id: int, target_id: int
    ) -> None:
        """Execute *action_id* for the pending decision and clear it."""
        self._lib.freeciv_ai_resolve_action_decision(actor_id, action_id, target_id)

    def cancel_action_decision(self, actor_id: int) -> None:
        """Cancel the pending action decision (no action taken)."""
        self._lib.freeciv_ai_cancel_action_decision(actor_id)

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
        extra_cmds: list[str] | None = None,
        saves_dir: str | None = None,
        username: str = "ai-player",
        auto_start: bool = True,
    ):
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
        from .server import FreecivServer

        server = await FreecivServer().start(
            port=port,
            maxplayers=maxplayers,
            aifill=aifill,
            endturn=endturn,
            timeout_secs=timeout_secs,
            extra_cmds=extra_cmds,
            saves_dir=saves_dir,
        )

        self.connect(host="localhost", port=port, username=username)

        if auto_start:
            if not await self.wait_for_hack():
                _logger.warning("Could not obtain hack level — /start may fail")
            self.start_game()

        return server
