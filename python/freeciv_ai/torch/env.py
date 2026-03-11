"""
FreecivEnv: async RL environment wrapping FreecivClient.

Observation
-----------
Flat float32 tensor of shape ``(map_w * map_h + n_units * 3,)``:
  - ``map_w * map_h`` values: per-tile known status, normalised to [0, 1]
    (0 = unknown, 0.5 = fogged, 1.0 = visible)
  - per unit: ``x / map_w``, ``y / map_h``, ``moves_left / moves_max``

Action space
------------
9 actions per unit:
  0 = skip, 1-8 = directions N NE E SE S SW W NW (matching Directions enum)

Reward
------
``+1`` per newly revealed tile this step, ``-0.01`` step penalty.

Log tasks
---------
The caller is responsible for calling ``start_log_tasks()`` / ``stop_log_tasks()``xg
around the full training session.  FreecivEnv does not manage them itself so
the pipe can be shared across many episodes.
"""

import asyncio
import tempfile
import logging

import torch

from freeciv_ai import FreecivClient, ClientState
from freeciv_ai.server import FreecivServer
from freeciv_ai.constants import Actions

log = logging.getLogger(__name__)

# known status → normalised float
_KNOWN_NORM = {0: 0.0, 1: 0.5, 2: 1.0}
_STEP_PENALTY = -0.01
_N_ACTIONS = 9  # 0=skip, 1..8 = directions

# Direction offsets: N NE E SE S SW W NW (matches Directions enum 0..7)
_DIR_DX = [0, 1, 1, 1, 0, -1, -1, -1]
_DIR_DY = [-1, -1, 0, 1, 1, 1, 0, -1]


def _dir_to_tile(x: int, y: int, direction: int) -> tuple[int, int]:
    return x + _DIR_DX[direction], y + _DIR_DY[direction]


def _make_action_mask(client: "FreecivClient", units: list, max_units: int) -> torch.Tensor:
    """
    Build a (max_units, 9) boolean action-validity mask.

    Action 0 (skip) is always valid.
    Actions 1-8 (directions N…NW) are valid if any of UNIT_MOVE / UNIT_MOVE2 /
    UNIT_MOVE3 reports non-negative feasibility for that unit + target tile.
    Units beyond len(units) are all-False except skip.
    """
    mask = torch.zeros(max_units, 9, dtype=torch.bool)
    mask[:, 0] = True  # skip is always legal
    for i, u in enumerate(units[:max_units]):
        uid, x, y = u["id"], u["x"], u["y"]
        for d in range(8):  # directions 0=N .. 7=NW → action indices 1..8
            tx, ty = _dir_to_tile(x, y, d)
            tidx = client.tile_index(tx, ty)
            if tidx < 0:
                continue
            for act in (Actions.UNIT_MOVE, Actions.UNIT_MOVE2, Actions.UNIT_MOVE3):
                if client.can_do_action(uid, act, tidx) >= 0:
                    mask[i, d + 1] = True
                    break
    return mask


class FreecivEnv:
    """
    Persistent-server async RL environment for unit exploration.

    The server and client are created once on the first :meth:`reset` call and
    reused across all episodes.  Each subsequent :meth:`reset` sends ``/endgame``
    to the running server (putting it back to lobby state), then ``/start`` to
    begin a fresh game — no port rebind, no TCP TIME_WAIT issues.

    Call :meth:`close` once at the very end of training to shut down.

    Usage::

        env = FreecivEnv(max_turns=20, port=5600)
        obs = await env.reset()          # starts server + game 1
        done = False
        while not done:
            actions = [0] * len(env.last_units)
            obs, reward, done, info = await env.step(actions)
        obs = await env.reset()          # ends game 1, starts game 2
        ...
        await env.close()                # shuts down server
    """

    action_space_size: int = _N_ACTIONS

    def __init__(
        self,
        max_turns: int = 20,
        port: int = 5600,
        max_units: int = 16,
    ) -> None:
        self.max_turns = max_turns
        self.port = port
        self.max_units = max_units

        self._client: FreecivClient | None = None
        self._server = None
        self._savedir: tempfile.TemporaryDirectory | None = None
        self._known: set[int] = set()
        self._turn: int = 0
        self.last_units: list[dict] = []
        self.last_mask: "torch.Tensor | None" = None
        self.map_w: int = 1
        self.map_h: int = 1

    @property
    def obs_size(self) -> int:
        return self.map_w * self.map_h + self.max_units * 3

    async def reset(self) -> torch.Tensor:
        """
        Start (or restart) a game and return the initial observation.

        First call: launches the server subprocess and connects the client.
        Subsequent calls: sends ``/endgame``, waits for C_S_OVER, reconnects
        via :meth:`FreecivClient.reconnect` (no ``client_main()`` re-run),
        then starts a new game — all on the same server and coroutine.
        """
        if self._server is None:
            # ── First call: start the server process ─────────────────────────
            self._savedir = tempfile.TemporaryDirectory()
            self._client = FreecivClient()
            self._server = await self._client.start_server(
                port=self.port,
                username="rl-agent",
                auto_start=False,  # we control /start ourselves
                saves_dir=self._savedir.name,
                extra_cmds=["/set autosaves 0"],
            )
            if not await self._client.wait_for_hack(timeout=10.0):
                raise RuntimeError("Failed to obtain hack level from server")
        else:
            # ── Subsequent calls: restart server, reconnect via C coroutine ──
            # Stopping the server closes the TCP connection; the background
            # poll loop processes the EOF and transitions the client state to
            # DISCONNECTED, freeing all game data cleanly.
            assert self._client is not None
            await self._server.stop()
            self._server = None
            if self._savedir is not None:
                self._savedir.cleanup()
                self._savedir = None

            # Wait for the poll loop to process the server disconnect.
            async with asyncio.timeout(5.0):
                while self._client.state != ClientState.DISCONNECTED:
                    await asyncio.sleep(0.05)

            # Start a fresh server on the same port (always in S_S_INITIAL).
            self._savedir = tempfile.TemporaryDirectory()
            self._server = await FreecivServer().start(
                port=self.port,
                saves_dir=self._savedir.name,
                extra_cmds=["/set autosaves 0"],
            )

            # Reconnect the existing C coroutine to the new server.
            await self._client.reconnect("localhost", self.port, "rl-agent")
            if not await self._client.wait_for_hack(timeout=10.0):
                raise RuntimeError("Failed to obtain hack level after reconnect")

        # ── Start a fresh game ────────────────────────────────────────────────
        self._client.start_game()

        async with asyncio.timeout(30.0):
            last_state = None
            while not self._client.in_game:
                cur_state = self._client.state
                if cur_state != last_state:
                    log.debug("waiting for in_game: state=%s", cur_state)
                    last_state = cur_state
                if cur_state == ClientState.DISCONNECTED:
                    raise ConnectionError("Server disconnected before game started")
                await asyncio.sleep(0.05)
        log.debug("in_game=True, state=%s", self._client.state)

        client = self._client
        self.map_w = client.map_width
        self.map_h = client.map_height

        await _wait_acting(client)
        self._known = self._visible_tile_indices()
        self._turn = 0
        self.last_units = client.get_units()[: self.max_units]
        self.last_mask = _make_action_mask(client, self.last_units, self.max_units)
        return self._make_obs()

    async def step(self, actions: list[int]) -> tuple[torch.Tensor, float, bool, dict]:
        """
        Apply one action per unit, end the turn, return ``(obs, reward, done, info)``.

        ``actions[i]`` is an integer in ``[0, N_ACTIONS)``:
          0 = skip, 1..8 = directions N NE E SE S SW W NW.
        """
        client = self._client
        assert client is not None, "call reset() first"

        units = self.last_units
        for i, unit in enumerate(units):
            if i >= len(actions):
                break
            act = actions[i]
            if act == 0:
                continue  # skip
            direction = act - 1  # 0=N .. 7=NW
            tile_x, tile_y = _dir_to_tile(unit["x"], unit["y"], direction)
            tile_idx = client.tile_index(tile_x, tile_y)
            if tile_idx >= 0:
                for _act in (Actions.UNIT_MOVE, Actions.UNIT_MOVE2, Actions.UNIT_MOVE3):
                    if client.can_do_action(unit["id"], _act, tile_idx) >= 0:
                        client.do_action(unit["id"], _act, tile_idx)
                        break

        turn_before = client.turn
        client.end_turn()

        # Poll until the server starts the next turn.  We cannot rely on
        # ``can_act`` staying False between turns (in a solo game it is
        # always True); instead we wait for ``client.turn`` to increment,
        # which requires at least one poll to flush the outgoing buffer.
        try:
            async with asyncio.timeout(60.0):
                while True:
                    if client.state == ClientState.DISCONNECTED:
                        raise ConnectionError("Server disconnected")
                    # Auto-cancel action decisions (e.g. entering a hut).
                    decision = client.get_action_decision()
                    if decision is not None:
                        client.cancel_action_decision(decision["actor_id"])
                        continue
                    if client.turn > turn_before:
                        break  # new turn has started
                    if not await client.poll(timeout=0.05):
                        raise ConnectionError("Server disconnected")
        except (ConnectionError, asyncio.TimeoutError):
            obs = self._make_obs()
            self._turn += 1
            info = {"turn": self._turn, "known_tiles": len(self._known)}
            return obs, _STEP_PENALTY, True, info

        new_known = self._visible_tile_indices()
        newly_revealed = len(new_known - self._known)
        self._known = new_known
        self._turn += 1

        reward = float(newly_revealed) + _STEP_PENALTY
        done = self._turn >= self.max_turns or not client.in_game
        self.last_units = client.get_units()[: self.max_units]
        self.last_mask = _make_action_mask(client, self.last_units, self.max_units)
        obs = self._make_obs()
        info = {"turn": self._turn, "known_tiles": len(self._known)}
        return obs, reward, done, info

    async def close(self) -> None:
        """Stop the server and clean up."""
        if self._server is not None:
            await self._server.stop()
            self._server = None
        if self._client is not None:
            self._client.stop()
            self._client = None
        if self._savedir is not None:
            self._savedir.cleanup()
            self._savedir = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _visible_tile_indices(self) -> set[int]:
        """Return tile indices of all currently or previously visible tiles."""
        assert self._client is not None
        tiles = self._client.get_map()
        return {t["index"] for t in tiles if t["known"] > 0}

    def _make_obs(self) -> torch.Tensor:
        """Build the flat float32 observation tensor."""
        assert self._client is not None
        client = self._client
        w, h = self.map_w, self.map_h

        map_vec = torch.zeros(w * h, dtype=torch.float32)
        for t in client.get_map():
            idx = t["index"]
            if 0 <= idx < w * h:
                map_vec[idx] = _KNOWN_NORM.get(t["known"], 0.0)

        unit_vec = torch.zeros(self.max_units * 3, dtype=torch.float32)
        for i, u in enumerate(self.last_units):
            base = i * 3
            unit_vec[base] = u["x"] / max(w, 1)
            unit_vec[base + 1] = u["y"] / max(h, 1)
            moves_max = u["moves_max"] or 1
            unit_vec[base + 2] = u["moves_left"] / moves_max

        return torch.cat([map_vec, unit_vec])




async def _wait_acting(client: FreecivClient, poll_interval: float = 0.05) -> None:
    """
    Wait until the client can act, cancelling any pending action decisions.

    Action decisions (e.g. entering a hut) block ``can_act`` until resolved.
    We auto-cancel them so the training loop never stalls.
    Raises ``ConnectionError`` if the server disconnects.
    """
    while not client.can_act:
        if client.state == ClientState.DISCONNECTED:
            raise ConnectionError("Server disconnected")
        decision = client.get_action_decision()
        if decision is not None:
            client.cancel_action_decision(decision["actor_id"])
            continue
        if not await client.poll(timeout=poll_interval):
            raise ConnectionError("Server disconnected")
