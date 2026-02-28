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
import sys

from freeciv_ai import FreecivClient, FreecivServer, ClientState, setup_logging
from freeciv_ai._logging import start_log_tasks, stop_log_tasks, set_prompt

log = logging.getLogger("freeciv_ai.lib")


# ---------------------------------------------------------------------------
# Async stdin helper
# ---------------------------------------------------------------------------

async def async_input(prompt: str) -> str:
    """
    Read one line from stdin without blocking the asyncio event loop.

    The event loop continues processing log tasks (and other awaitables)
    while waiting for the user to press Enter.  Since asyncio is
    single-threaded, log messages can only appear between keystrokes —
    never mid-character — so the prompt is always redrawn cleanly.
    """
    loop = asyncio.get_running_loop()
    fut: asyncio.Future[str] = loop.create_future()

    def _readable() -> None:
        loop.remove_reader(sys.stdin.fileno())
        line = sys.stdin.readline()
        if not fut.done():
            fut.set_result(line)

    sys.stdout.write(prompt)
    sys.stdout.flush()
    set_prompt(prompt)
    loop.add_reader(sys.stdin.fileno(), _readable)
    try:
        return (await fut).rstrip("\n")
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
    print(f"=== Units ({len(units)}) ===")
    for u in units:
        print(f"  [{u['id']:5d}] {u['type']:20s}  "
              f"({u['x']:3d},{u['y']:3d})  "
              f"HP {u['hp']}/{u['hp_max']}  "
              f"moves {u['moves_left']}/{u['moves_max']}")


def cmd_end(client: FreecivClient) -> None:
    if not client.can_act:
        print("Cannot issue orders — not your turn.")
        return
    client.end_turn()
    print("Turn ended.")


def cmd_help() -> None:
    print(
        "\n=== Commands ===\n"
        "  units         — list your units\n"
        "  end           — end your turn\n"
        "  poll          — process server packets\n"
        "  cmd <command> — send a server command (requires hack level)\n"
        "  hack          — check hack access level\n"
        "  help          — show this message\n"
        "  quit          — disconnect and exit\n"
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
    client.move_unit(uid, d)


# ---------------------------------------------------------------------------
# Async REPL
# ---------------------------------------------------------------------------

async def run_cli(client: FreecivClient) -> None:
    cmd_help()

    # Background task: keep pumping the server socket so responses arrive
    # immediately, even while the REPL is blocked in async_input().
    async def _net_loop() -> None:
        while client.state != ClientState.DISCONNECTED:
            await client.poll(timeout=0.1)

    net_task = asyncio.create_task(_net_loop(), name="net-poll")

    try:
        while True:
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
                line = (await async_input(f">{turn_info} ")).strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break

            if not line:
                continue

            tokens = line.split()
            cmd    = tokens[0].lower()

            if cmd == "units":
                cmd_units(client)
            elif cmd == "end":
                cmd_end(client)
            elif cmd == "move":
                cmd_move(client, tokens[1:])
            elif cmd == "poll":
                alive = await client.poll(timeout=0.5)
                print(f"State: {client.state.name}, connected: {alive}")
            elif cmd == "cmd":
                if len(tokens) < 2:
                    print("Usage: cmd <server command>")
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
    finally:
        net_task.cancel()
        try:
            await net_task
        except asyncio.CancelledError:
            pass


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

    server: FreecivServer | None = None

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

            while not client.in_game:
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
            while not client.in_game:
                if not await client.poll(timeout=0.1):
                    print("Disconnected before game started.", file=sys.stderr)
                    sys.exit(1)
            print("Game started!\n")

        try:
            await run_cli(client)
        finally:
            print("\nDisconnecting…")
            if server:
                await server.stop()
            await stop_log_tasks()


if __name__ == "__main__":
    asyncio.run(main())
