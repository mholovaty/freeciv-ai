"""
play.py — Run a trained ExplorerPolicy against a live Freeciv server.

By default the script connects, waits passively for the operator to /start
the game, plays, then exits.  This is the right mode for multi-agent setups
where several AI instances connect as separate players and a human controls
the server lifecycle.

Pass ``--auto-start`` to have the script send /start itself (single-player /
training convenience; requires hack level, i.e. localhost only).

See docs/play.md for a full walkthrough.
"""

import argparse
import asyncio
import logging
from pathlib import Path

import torch

from freeciv_ai import FreecivClient, ClientState, setup_logging
from freeciv_ai._logging import start_log_tasks, stop_log_tasks
from freeciv_ai.constants import Actions

from .env import _dir_to_tile, _wait_acting, _KNOWN_NORM, _make_action_mask
from .model import ExplorerPolicy

log = logging.getLogger(__name__)

_DIR_NAMES = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]


def _try_move(client: FreecivClient, uid: int, tidx: int) -> "int | None":
    """Try UNIT_MOVE, UNIT_MOVE2, UNIT_MOVE3. Return action id used, or None if all blocked."""
    for act in (Actions.UNIT_MOVE, Actions.UNIT_MOVE2, Actions.UNIT_MOVE3):
        if client.can_do_action(uid, act, tidx) >= 0:
            client.do_action(uid, act, tidx)
            return act
    return None


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Play Freeciv with a trained ExplorerPolicy")
    p.add_argument("--checkpoint", type=Path, required=True, help="Path to .pt checkpoint file")
    p.add_argument("--host", default="localhost", help="Server hostname")
    p.add_argument("--port", type=int, default=5600, help="Server port")
    p.add_argument("--username", default="rl-agent", help="Player name to connect as")
    p.add_argument("--max-units", type=int, default=16, help="Max units tracked (must match training)")
    p.add_argument("--max-turns", type=int, default=200, help="Stop after this many turns")
    p.add_argument("--delay", type=float, default=0.0,
                   help="Seconds to wait before ending each turn (use 1–3 for slow replay)")
    p.add_argument("--episodes", type=int, default=1,
                   help="Number of games to play back-to-back. "
                        "After each game the script waits for the operator to start the next one.")
    p.add_argument("--auto-start", action="store_true",
                   help="Send /start to the server after connecting instead of waiting for the "
                        "operator to start the game. Requires hack level (localhost only). "
                        "For multi-episode runs also sends /endgame between games.")
    p.add_argument("--log-level", default="INFO")
    return p.parse_args()


def _build_obs(client: FreecivClient, max_units: int) -> torch.Tensor:
    """Build the same flat float32 observation tensor as FreecivEnv._make_obs."""
    w, h = client.map_width, client.map_height

    map_vec = torch.zeros(w * h, dtype=torch.float32)
    for t in client.get_map():
        idx = t["index"]
        if 0 <= idx < w * h:
            map_vec[idx] = _KNOWN_NORM.get(t["known"], 0.0)

    units = client.get_units()[:max_units]
    unit_vec = torch.zeros(max_units * 3, dtype=torch.float32)
    for i, u in enumerate(units):
        base = i * 3
        unit_vec[base]     = u["x"] / max(w, 1)
        unit_vec[base + 1] = u["y"] / max(h, 1)
        moves_max = u["moves_max"] or 1
        unit_vec[base + 2] = u["moves_left"] / moves_max

    return torch.cat([map_vec, unit_vec])


def _count_known(client: FreecivClient) -> int:
    return sum(1 for t in client.get_map() if t["known"] > 0)


async def _play_game(
    client: FreecivClient,
    policy: ExplorerPolicy,
    args: argparse.Namespace,
    episode: int,
) -> None:
    """Play one full game with the loaded policy."""
    log.info("=== Episode %d: waiting for turn ===", episode)

    known_before = _count_known(client)
    turn = 0

    while client.in_game and turn < args.max_turns:
        await _wait_acting(client)

        if not client.in_game:
            break

        units = client.get_units()[:args.max_units]
        n_units = len(units)
        obs = _build_obs(client, args.max_units)
        mask = _make_action_mask(client, units, args.max_units)

        acts, _ = policy.select_actions(obs, n_units or 1, mask)

        # Execute and log each unit's action
        for i, unit in enumerate(units):
            act = acts[i] if i < len(acts) else 0
            if act == 0:
                log.info(
                    "  turn %3d  unit %d @ (%d,%d)  → skip",
                    turn + 1, unit["id"], unit["x"], unit["y"],
                )
                continue

            direction = act - 1
            tile_x, tile_y = _dir_to_tile(unit["x"], unit["y"], direction)
            tile_idx = client.tile_index(tile_x, tile_y)

            if tile_idx >= 0 and _try_move(client, unit["id"], tile_idx) is not None:
                log.info(
                    "  turn %3d  unit %d @ (%d,%d)  → move %s → (%d,%d)",
                    turn + 1, unit["id"], unit["x"], unit["y"],
                    _DIR_NAMES[direction], tile_x, tile_y,
                )
            else:
                log.info(
                    "  turn %3d  unit %d @ (%d,%d)  → move %s blocked",
                    turn + 1, unit["id"], unit["x"], unit["y"],
                    _DIR_NAMES[direction],
                )

        known_after = _count_known(client)
        newly_revealed = known_after - known_before
        known_before = known_after
        turn += 1

        log.info(
            "turn %3d  known=%d  newly_revealed=%+d",
            turn, known_after, newly_revealed,
        )

        if args.delay > 0:
            await asyncio.sleep(args.delay)

        client.end_turn()

    log.info(
        "=== Episode %d done after %d turns, %d tiles known ===",
        episode, turn, known_before,
    )


async def play(args: argparse.Namespace) -> None:
    setup_logging(level=getattr(logging, args.log_level.upper()))
    await start_log_tasks()

    try:
        await _play_loop(args)
    finally:
        await stop_log_tasks()


async def _play_loop(args: argparse.Namespace) -> None:
    log.info("Loading checkpoint: %s", args.checkpoint)
    ckpt = torch.load(args.checkpoint, weights_only=True)

    client = FreecivClient()
    log.info("Connecting to %s:%d as %r ...", args.host, args.port, args.username)
    client.connect(host=args.host, port=args.port, username=args.username)

    # Wait until we're in the lobby or in-game
    async with asyncio.timeout(30.0):
        while client.state == ClientState.INITIAL:
            await asyncio.sleep(0.1)
    log.info("Connected, state=%s", client.state)

    # Wait for the game to start
    async with asyncio.timeout(60.0):
        while not client.in_game:
            if client.state == ClientState.DISCONNECTED:
                raise ConnectionError("Server disconnected before game started")
            await asyncio.sleep(0.1)
    log.info("Game started, map=%dx%d", client.map_width, client.map_height)

    # Build model with the correct obs_size derived from the live map
    obs_size = client.map_width * client.map_height + args.max_units * 3
    # Infer hidden size from checkpoint weights
    hidden_size = ckpt["model"]["trunk.0.weight"].shape[0]
    policy = ExplorerPolicy(obs_size=obs_size, max_units=args.max_units, hidden_size=hidden_size)
    policy.load_state_dict(ckpt["model"])
    policy.eval()
    log.info(
        "Policy loaded: obs_size=%d  max_units=%d  hidden=%d  (trained ep=%s)",
        obs_size, args.max_units, hidden_size, ckpt.get("episode", "?"),
    )

    try:
        for ep in range(1, args.episodes + 1):
            if ep > 1:
                # Wait for the previous game to fully end, then start (or wait for) the next one.
                async with asyncio.timeout(15.0):
                    while client.in_game:
                        await asyncio.sleep(0.1)

                if args.auto_start:
                    if not client.has_hack:
                        log.warning("No hack level — cannot /start for episode %d", ep)
                        break
                    client.start_game()
                else:
                    log.info("Episode %d ended. Waiting for operator to start the next game...", ep - 1)

                async with asyncio.timeout(300.0):
                    while not client.in_game:
                        if client.state == ClientState.DISCONNECTED:
                            raise ConnectionError("Disconnected waiting for next game")
                        await asyncio.sleep(0.2)
                log.info("New game started for episode %d", ep)

            await _play_game(client, policy, args, ep)
    finally:
        client.stop()


def main() -> None:
    asyncio.run(play(_parse_args()))


if __name__ == "__main__":
    main()
