#!/usr/bin/env python3
"""
Freeciv AI client — interactive CLI built on top of libfreeciv_ai.so.

Usage::

    # Connect to an already-running server:
    python client.py [--host HOST] [--port PORT] [--username NAME]

    # Start a local server, connect, and auto-start a game:
    python client.py --local [--port PORT] [--endturn N] [--timeout N]
"""

import argparse
import asyncio
import logging
import signal
import sys

from freeciv_ai import FreecivClient, FreecivServer, ClientState, setup_logging
from freeciv_ai._logging import start_log_tasks, stop_log_tasks, set_prompt
from freeciv_ai.constants import Actions, TileKnown

log = logging.getLogger("freeciv_ai.lib")


# ---------------------------------------------------------------------------
# Async stdin helper
# ---------------------------------------------------------------------------

async def async_input(prompt: str, stop_event: asyncio.Event | None = None) -> str:
    """
    Read one line from stdin without blocking the asyncio event loop.

    If *stop_event* is provided and becomes set before the user presses Enter,
    raises ``EOFError`` so the caller can exit cleanly (Ctrl+C support).
    """
    loop = asyncio.get_running_loop()
    line_fut: asyncio.Future[str] = loop.create_future()

    def _readable() -> None:
        loop.remove_reader(sys.stdin.fileno())
        line = sys.stdin.readline()
        if not line_fut.done():
            line_fut.set_result(line)

    sys.stdout.write(prompt)
    sys.stdout.flush()
    set_prompt(prompt)
    loop.add_reader(sys.stdin.fileno(), _readable)
    try:
        if stop_event is not None:
            stop_fut = asyncio.ensure_future(stop_event.wait())
            try:
                done, _ = await asyncio.wait(
                    {line_fut, stop_fut},
                    return_when=asyncio.FIRST_COMPLETED,
                )
            finally:
                if not stop_fut.done():
                    stop_fut.cancel()
            if stop_event.is_set() and not line_fut.done():
                loop.remove_reader(sys.stdin.fileno())
                raise EOFError("interrupted by stop_event")
            return line_fut.result().rstrip("\n")
        else:
            return (await line_fut).rstrip("\n")
    except asyncio.CancelledError:
        loop.remove_reader(sys.stdin.fileno())
        raise
    finally:
        set_prompt("")


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_units(client: FreecivClient) -> None:
    units = client.get_units()
    if not units:
        print("No units (or no player connected).")
        return
    print(f"=== Your units ({len(units)}) ===")
    for u in units:
        print(f"  [{u['id']:5d}] {u['type']:20s}  "
              f"({u['x']:3d},{u['y']:3d})  "
              f"HP {u['hp']}/{u['hp_max']}  "
              f"moves {u['moves_left']}/{u['moves_max']}")


def cmd_allunits(client: FreecivClient) -> None:
    """Print all units visible on the map (own + enemy)."""
    mine: list[dict] = []
    enemy: list[dict] = []

    seen_tiles: set[tuple] = set()
    for t in client.get_map():
        if t["known"] != TileKnown.KNOWN_SEEN or t["n_units"] == 0:
            continue
        key = (t["x"], t["y"])
        if key in seen_tiles:
            continue
        seen_tiles.add(key)
        for u in client.get_tile_units(t["x"], t["y"]):
            bucket = mine if u.get("owner", -2) == -2 else enemy
            # get_tile_units doesn't have owner; separate using your own list
            bucket.append(u)

    # Split own vs foreign by cross-referencing get_units()
    own_ids = {u["id"] for u in client.get_units()}
    mine_list, enemy_list = [], []
    for t in client.get_map():
        if t["known"] != TileKnown.KNOWN_SEEN or t["n_units"] == 0:
            continue
        for u in client.get_tile_units(t["x"], t["y"]):
            if u["id"] in own_ids:
                mine_list.append(u)
            else:
                enemy_list.append(u)

    if mine_list:
        print(f"=== Your units ({len(mine_list)}) ===")
        for u in mine_list:
            print(f"  [{u['id']:5d}] {u['type']:20s}  "
                  f"({u['x']:3d},{u['y']:3d})  "
                  f"HP {u['hp']}/{u['hp_max']}  "
                  f"moves {u['moves_left']}/{u['moves_max']}")
    else:
        print("No own units visible.")

    if enemy_list:
        print(f"=== Visible enemy/foreign units ({len(enemy_list)}) ===")
        for u in enemy_list:
            print(f"  [{u['id']:5d}] {u['type']:20s}  "
                  f"({u['x']:3d},{u['y']:3d})  "
                  f"HP {u['hp']}/{u['hp_max']}")
    else:
        print("No enemy units visible.")


def cmd_end(client: FreecivClient) -> None:
    if not client.can_act:
        print("Cannot issue orders — not your turn.")
        return
    client.end_turn()
    print("Turn ended.")


def cmd_tile(client: FreecivClient, args: list[str]) -> None:
    """tile <x> <y>  — show terrain, city, and units at a tile."""
    if len(args) != 2:
        print("Usage: tile <x> <y>")
        return
    try:
        x, y = int(args[0]), int(args[1])
    except ValueError:
        print("x and y must be integers.")
        return

    # Find the tile in the map snapshot
    tile = None
    for t in client.get_map():
        if t["x"] == x and t["y"] == y:
            tile = t
            break

    if tile is None:
        print(f"Tile ({x},{y}) not found (map size "
              f"{client.map_width}×{client.map_height}).")
        return

    known_name = {0: "Unknown", 1: "Fogged", 2: "Visible"}.get(
        tile["known"], str(tile["known"]))
    print(f"=== Tile ({x},{y}) ===")
    print(f"  Index   : {tile['index']}")
    print(f"  Known   : {known_name}")
    print(f"  Terrain : {tile['terrain'] or '—'}")
    print(f"  Owner   : {tile['owner'] if tile['owner'] >= 0 else 'None'}")
    if tile["city_id"] >= 0:
        print(f"  City    : {tile['city_name']} (id {tile['city_id']})")
    else:
        print(f"  City    : None")

    units = client.get_tile_units(x, y)
    if units:
        print(f"  Units ({len(units)}):")
        for u in units:
            print(f"    [{u['id']:5d}] {u['type']:20s}  "
                  f"HP {u['hp']}/{u['hp_max']}  "
                  f"moves {u['moves_left']}/{u['moves_max']}")
    else:
        print("  Units   : None")


def cmd_cities(client: FreecivClient) -> None:
    cities = client.get_cities()
    if not cities:
        print("No cities (or no player connected).")
        return
    print(f"=== Your cities ({len(cities)}) ===")
    for c in cities:
        print(f"  [{c['id']:5d}] {c['name']:20s}  "
              f"({c['x']:3d},{c['y']:3d})  "
              f"size {c['size']}  "
              f"food {c['food_surplus']:+d}  "
              f"prod {c['prod_surplus']:+d}  "
              f"trade {c['trade']:+d}")


def cmd_help() -> None:
    print(
        "\n=== Commands ===\n"
        "  units              — list your units\n"
        "  allunits           — list all visible units (own + enemy)\n"
        "  cities             — list your cities\n"
        "  tile <x> <y>       — show tile info and units at (x,y)\n"
        "  move <id> <dir>    — move unit one step: N NE E SE S SW W NW\n"
        "  go <id> <x> <y>   — move unit to tile (ACTION_UNIT_MOVE)\n"
        "  fortify <id>       — fortify unit\n"
        "  found <id> [name]  — found a city (settler must be on tile)\n"
        "  end                — end your turn\n"
        "  poll               — process server packets\n"
        "  server <command>   — send a server command (requires hack level)\n"
        "  hack               — check hack access level\n"
        "  help               — show this message\n"
        "  quit               — disconnect and exit\n"
    )


def cmd_move(client: FreecivClient, args: list[str]) -> None:
    """move <unit_id> <direction>   direction: N NE E SE S SW W NW"""
    dirs = {"n": 0, "ne": 1, "e": 2, "se": 3, "s": 4, "sw": 5, "w": 6, "nw": 7}
    if len(args) != 2:
        print("Usage: move <unit_id> <N|NE|E|SE|S|SW|W|NW>")
        return
    try:
        uid = int(args[0])
    except ValueError:
        print(f"Invalid unit id: {args[0]}")
        return
    d = dirs.get(args[1].lower())
    if d is None:
        print(f"Unknown direction '{args[1]}'. Use: N NE E SE S SW W NW")
        return
    unit = next((u for u in client.get_units() if u["id"] == uid), None)
    if unit is None:
        print(f"Unit {uid} not found in your unit list.")
        return
    if unit["moves_left"] <= 0:
        print(f"Unit {uid} has no moves left this turn.")
        return
    client.move_unit(uid, d)


def cmd_go(client: FreecivClient, args: list[str]) -> None:
    """go <unit_id> <x> <y>  — request unit move to tile via ACTION_UNIT_MOVE"""
    if len(args) != 3:
        print("Usage: go <unit_id> <x> <y>")
        return
    try:
        uid, x, y = int(args[0]), int(args[1]), int(args[2])
    except ValueError:
        print("unit_id, x, y must be integers.")
        return
    tidx = client.tile_index(x, y)
    if tidx < 0:
        print(f"Tile ({x},{y}) is out of map bounds.")
        return
    prob = client.can_do_action(uid, Actions.UNIT_MOVE, tidx)
    if prob < 0:
        # Try alternate move actions (UNIT_MOVE2, UNIT_MOVE3)
        for act in (Actions.UNIT_MOVE2, Actions.UNIT_MOVE3):
            prob = client.can_do_action(uid, act, tidx)
            if prob >= 0:
                client.do_action(uid, act, tidx)
                return
        print(f"Unit {uid} cannot move to ({x},{y}) (action impossible).")
        return
    client.do_action(uid, Actions.UNIT_MOVE, tidx)


def cmd_fortify(client: FreecivClient, args: list[str]) -> None:
    """fortify <unit_id>"""
    if len(args) != 1:
        print("Usage: fortify <unit_id>")
        return
    try:
        uid = int(args[0])
    except ValueError:
        print(f"Invalid unit id: {args[0]}")
        return
    tidx = client.tile_index(
        *next(
            ((u["x"], u["y"]) for u in client.get_units() if u["id"] == uid),
            (0, 0),
        )
    )
    prob = client.can_do_action(uid, Actions.FORTIFY, tidx)
    if prob < 0:
        prob = client.can_do_action(uid, Actions.FORTIFY2, tidx)
        if prob < 0:
            print(f"Unit {uid} cannot fortify here.")
            return
        client.do_action(uid, Actions.FORTIFY2, tidx)
    else:
        client.do_action(uid, Actions.FORTIFY, tidx)


def cmd_found(client: FreecivClient, args: list[str]) -> None:
    """found <unit_id> [city_name]"""
    if not args:
        print("Usage: found <unit_id> [city_name]")
        return
    try:
        uid = int(args[0])
    except ValueError:
        print(f"Invalid unit id: {args[0]}")
        return
    city_name = " ".join(args[1:]) if len(args) > 1 else ""

    unit_pos = next(
        ((u["x"], u["y"]) for u in client.get_units() if u["id"] == uid),
        None,
    )
    if unit_pos is None:
        print(f"Unit {uid} not found in your unit list.")
        return
    tidx = client.tile_index(*unit_pos)
    prob = client.can_do_action(uid, Actions.FOUND_CITY, tidx)
    if prob < 0:
        print(f"Unit {uid} cannot found a city here.")
        return
    client.do_action(uid, Actions.FOUND_CITY, tidx, name=city_name)


# ---------------------------------------------------------------------------
# Async REPL
# ---------------------------------------------------------------------------

async def run_cli(client: FreecivClient,
                  stop_event: asyncio.Event) -> None:
    cmd_help()

    while not stop_event.is_set():
            state = client.state
            if state == ClientState.DISCONNECTED:
                print("Server disconnected.")
                break

            turn_info = ""
            if state == ClientState.RUNNING:
                turn_info = f" [Turn {client.turn}"
                turn_info += ", your turn" if client.can_act else ""
                turn_info += "]"

            try:
                line = (await async_input(f">{turn_info} ", stop_event)).strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break

            if not line:
                continue

            tokens = line.split()
            cmd    = tokens[0].lower()

            if cmd == "units":
                cmd_units(client)
            elif cmd == "allunits":
                cmd_allunits(client)
            elif cmd == "cities":
                cmd_cities(client)
            elif cmd == "tile":
                cmd_tile(client, tokens[1:])
            elif cmd == "end":
                cmd_end(client)
            elif cmd == "move":
                cmd_move(client, tokens[1:])
            elif cmd == "go":
                cmd_go(client, tokens[1:])
            elif cmd == "fortify":
                cmd_fortify(client, tokens[1:])
            elif cmd == "found":
                cmd_found(client, tokens[1:])
            elif cmd == "poll":
                alive = await client.poll(timeout=0.5)
                print(f"State: {client.state.name}, connected: {alive}")
            elif cmd == "server":
                if len(tokens) < 2:
                    print("Usage: server <server command>")
                else:
                    client.send_command(" ".join(tokens[1:]))
            elif cmd == "hack":
                print(f"Hack level: {'YES' if client.has_hack else 'NO'}")
            elif cmd in ("help", "?"):
                cmd_help()
            elif cmd in ("quit", "exit", "q"):
                break
            else:
                print(f"Unknown command '{cmd}'. Type 'help'.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Freeciv AI client")
    p.add_argument("--host",      default="localhost")
    p.add_argument("--port",      type=int, default=5556)
    p.add_argument("--username",  default="ai-player")
    p.add_argument("--data-path", default=None,
                   help="Path to freeciv/data (auto-detected if omitted)")
    p.add_argument("--local", action="store_true",
                   help="Start a local server, connect, and auto-start a game")
    p.add_argument("--endturn", type=int, default=0,
                   help="(--local) End game after N turns (0 = unlimited)")
    p.add_argument("--timeout", type=int, default=0,
                   help="(--local) Per-turn time limit in seconds (0 = unlimited)")
    p.add_argument("--verbose", action="store_true",
                   help="Show DEBUG-level (LOG_VERBOSE) messages from the C library")
    return p.parse_args()


async def main() -> None:
    args = parse_args()
    setup_logging(level=logging.DEBUG if args.verbose else logging.INFO)
    await start_log_tasks()

    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()
    _sigint_count = 0

    def _on_signal() -> None:
        nonlocal _sigint_count
        _sigint_count += 1
        if _sigint_count == 1:
            print("\r\033[2KInterrupt — shutting down (Ctrl+C again to force).",
                  flush=True)
            stop_event.set()
        else:
            # Second signal: exit immediately without waiting for cleanup
            import os
            os._exit(1)

    loop.add_signal_handler(signal.SIGINT,  _on_signal)
    loop.add_signal_handler(signal.SIGTERM, _on_signal)

    server: FreecivServer | None = None

    try:
        with FreecivClient() as client:
            client.init(data_path=getattr(args, "data_path", None))

            if args.local:
                print(f"Starting local server on port {args.port}…")
                try:
                    server = await client.start_server(
                        port=args.port,
                        username=args.username,
                        endturn=args.endturn,
                        timeout_secs=args.timeout,
                        auto_start=True,
                    )
                except (TimeoutError, ConnectionError) as exc:
                    print(f"Error: {exc}", file=sys.stderr)
                    sys.exit(1)

                while not client.in_game and not stop_event.is_set():
                    if not await client.poll(timeout=0.1):
                        print("Disconnected before game started.", file=sys.stderr)
                        sys.exit(1)
                print("Game started!\n")
            else:
                print(f"Connecting to {args.host}:{args.port} as '{args.username}'…")
                try:
                    client.connect(host=args.host, port=args.port,
                                   username=args.username)
                except ConnectionError as exc:
                    print(f"Error: {exc}", file=sys.stderr)
                    sys.exit(1)

                print("Connected. Waiting for game to start…")
                while not client.in_game and not stop_event.is_set():
                    if not await client.poll(timeout=0.1):
                        print("Disconnected before game started.", file=sys.stderr)
                        sys.exit(1)
                print("Game started!\n")

            await run_cli(client, stop_event)
    finally:
        print("\nDisconnecting…")
        if server is not None:
            server.force_kill()
        await stop_log_tasks()


if __name__ == "__main__":
    asyncio.run(main())
