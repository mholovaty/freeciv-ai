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
import shutil

from freeciv_ai.map_renderer import (
    BG_UNKNOWN, FG_BORDER, FG_CONTENT, MAP_RESET,
    MapCanvas, map_legend, map_pos_to_native,
    parse_map_range, rpad, render_isohex, render_isohex_centered,
    terrain_bg, units_panel_lines, visible_len,
)
import signal
import sys

try:
    import readline as _readline
    _readline.parse_and_bind("Control-l: clear-screen")
except ImportError:
    pass

from freeciv_ai import FreecivClient, FreecivServer, ClientState, setup_logging
from freeciv_ai._logging import start_log_tasks, stop_log_tasks, set_prompt
from freeciv_ai.constants import Actions, TileKnown

log = logging.getLogger("freeciv_ai.lib")





async def async_input(prompt: str, stop_event: asyncio.Event | None = None) -> str:
    """
    Read one line from stdin via input(), which goes through GNU readline so
    key bindings (Ctrl+L clear-screen, history, etc.) work correctly.

    If *stop_event* is provided and becomes set before the user presses Enter,
    raises ``EOFError`` so the caller can exit cleanly.
    """
    loop = asyncio.get_running_loop()
    set_prompt(prompt)
    try:
        line_fut: asyncio.Future[str] = loop.run_in_executor(None, input, prompt)
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
            if stop_event.is_set() and line_fut not in done:
                raise EOFError("interrupted by stop_event")
            return line_fut.result()
        else:
            return await line_fut
    finally:
        set_prompt("")


def cmd_units(client: FreecivClient) -> None:
    units = client.get_units()
    if not units:
        print("No units (or no player connected).")
        return
    print(f"=== Your units ({len(units)}) ===")
    for u in units:
        print(
            f"  [{u['id']:5d}] {u['type']:20s}  "
            f"({u['x']:3d},{u['y']:3d})  "
            f"HP {u['hp']}/{u['hp_max']}  "
            f"moves {u['moves_left']}/{u['moves_max']}"
        )


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
            print(
                f"  [{u['id']:5d}] {u['type']:20s}  "
                f"({u['x']:3d},{u['y']:3d})  "
                f"HP {u['hp']}/{u['hp_max']}  "
                f"moves {u['moves_left']}/{u['moves_max']}"
            )
    else:
        print("No own units visible.")

    if enemy_list:
        print(f"=== Visible enemy/foreign units ({len(enemy_list)}) ===")
        for u in enemy_list:
            print(
                f"  [{u['id']:5d}] {u['type']:20s}  "
                f"({u['x']:3d},{u['y']:3d})  "
                f"HP {u['hp']}/{u['hp_max']}"
            )
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
        print(
            f"Tile ({x},{y}) not found (map size "
            f"{client.map_width}×{client.map_height})."
        )
        return

    known_name = {0: "Unknown", 1: "Fogged", 2: "Visible"}.get(
        tile["known"], str(tile["known"])
    )
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
            print(
                f"    [{u['id']:5d}] {u['type']:20s}  "
                f"HP {u['hp']}/{u['hp_max']}  "
                f"moves {u['moves_left']}/{u['moves_max']}"
            )
    else:
        print("  Units   : None")


def cmd_topology(client: FreecivClient) -> None:
    topo = client.map_topology_id
    wrap = client.map_wrap_id
    flags = []
    if topo & 1:
        flags.append("ISO")
    if topo & 2:
        flags.append("Hex")
    wrapping = []
    if wrap & 1:
        wrapping.append("X")
    if wrap & 2:
        wrapping.append("Y")
    print(f"=== Map Topology ===")
    print(f"  Size     : {client.map_width}×{client.map_height}")
    print(f"  Topology : {', '.join(flags) or 'Flat'} (id={topo})")
    print(f"  Wrapping : {'Wrap' + '+'.join(wrapping) if wrapping else 'None'} (id={wrap})")


def _city_line(c: dict) -> str:
    """One-line summary of a city for panel / list display."""
    job = (f"{c['shield_stock']}/{c['prod_cost']} {c['prod_name']}"
           if c.get("prod_name") else "idle")
    food_bar = f"{c['food_stock']}/{c['granary_size']}"
    return (
        f"[{c['id']:4d}] {c['name']:16s}"
        f" sz{c['size']}"
        f" \033[32mfd{c['food_surplus']:+d}\033[0m({food_bar})"
        f" \033[33msh{c['prod_surplus']:+d}\033[0m"
        f" \033[36msc{c['science']:+d}\033[0m"
        f" tr{c['trade']:+d}"
        f"  [{job}]"
    )


def cities_panel_lines(cities: list[dict]) -> list[str]:
    """Format cities as a list of strings for the display panel."""
    if not cities:
        return ["(no cities)"]
    lines = [f"=== Cities ({len(cities)}) ==="]
    for c in cities:
        lines.append(_city_line(c))
    return lines


def cmd_cities(client: FreecivClient) -> None:
    cities = client.get_cities()
    if not cities:
        print("No cities (or no player connected).")
        return
    print(f"=== Your cities ({len(cities)}) ===")
    for c in cities:
        print(_city_line(c))


def _wrapped_avg(values: list[int], size: int) -> int:
    """Wrap-aware average — correct across the seam (e.g. x=0 and x=15 → 15/0 not 7)."""
    ref = values[0]
    adjusted = []
    for v in values:
        d = (v - ref) % size
        if d > size // 2:
            d -= size
        adjusted.append(ref + d)
    return round(sum(adjusted) / len(adjusted)) % size


def _init_map_center(client: "FreecivClient") -> None:
    """Set _map_center to the wrap-aware native-coord average of player units."""
    global _map_center
    units = client.get_units()
    if not units:
        return
    map_w = client.map_width
    map_h = client.map_height
    nat_xs, nat_ys = [], []
    for u in units:
        nx, ny = map_pos_to_native(u["x"], u["y"], map_w)
        nat_xs.append(nx)
        nat_ys.append(ny)
    _map_center = (_wrapped_avg(nat_xs, map_w), _wrapped_avg(nat_ys, map_h))


def cmd_map(client: FreecivClient, args: list[str]) -> None:
    """map [x1:x2 y1:y2] | map center <x> <y> | map legend"""
    if args and args[0] == "legend":
        print(map_legend())
        return

    topo = client.map_topology_id
    if topo != 3:
        print(f"map command only supports iso-hex topology (id=3); current id={topo}.")
        return

    global _map_center

    tiles = client.get_map()
    units = client.get_units()

    # Handle "map center [x y]" — set/query persistent view centre
    if args and args[0] == "center":
        coord_tokens = [a.rstrip(",") for a in args[1:] if a.rstrip(",")]
        if len(coord_tokens) >= 2:
            try:
                _map_center = (int(coord_tokens[0]), int(coord_tokens[1]))
            except ValueError:
                print("x and y must be integers.")
                return
        elif len(coord_tokens) == 0 and _map_center is None:
            print("Centre not set. Usage: map center <x> <y>")
            return
        # render centred (using existing or newly set centre)
        cx, cy = _map_center  # type: ignore[misc]
        term = shutil.get_terminal_size(fallback=(80, 24))
        print(render_isohex_centered(
            tiles, units, client.map_width, client.map_height,
            cx, cy, term.columns, term.lines,
        ))
        return

    # No args and centre is set → centred render
    if not args and _map_center is not None:
        cx, cy = _map_center
        term = shutil.get_terminal_size(fallback=(80, 24))
        print(render_isohex_centered(
            tiles, units, client.map_width, client.map_height,
            cx, cy, term.columns, term.lines,
        ))
        return

    # Two plain integers (no ':') = pan delta from current centre
    if (len(args) == 2
            and ":" not in args[0] and ":" not in args[1]
            and args[0] not in ("center", "legend")):
        try:
            dx, dy = int(args[0]), int(args[1])
        except ValueError:
            pass
        else:
            if _map_center is None:
                print("No centre set. Use 'map center <x> <y>' first.")
                return
            cx, cy = _map_center
            _map_center = (
                (cx + dx) % client.map_width,
                (cy + dy) % client.map_height,
            )
            cx, cy = _map_center
            term = shutil.get_terminal_size(fallback=(80, 24))
            print(render_isohex_centered(
                tiles, units, client.map_width, client.map_height,
                cx, cy, term.columns, term.lines,
            ))
            return

    # Slice render
    x_range: tuple[int, int] | None = None
    y_range: tuple[int, int] | None = None

    if len(args) >= 1:
        try:
            x_range = parse_map_range(args[0])
        except ValueError as e:
            print(f"Bad x range: {e}")
            print("Usage: map [x1:x2 y1:y2]  |  map <dx> <dy>  |  map center <x> <y>")
            return
    if len(args) >= 2:
        try:
            y_range = parse_map_range(args[1])
        except ValueError as e:
            print(f"Bad y range: {e}")
            print("Usage: map [x1:x2 y1:y2]  |  map <dx> <dy>  |  map center <x> <y>")
            return

    print(render_isohex(
        tiles, units, client.map_width, client.map_height,
        x_range, y_range,
    ))


def cmd_display(client: "FreecivClient") -> None:
    """display — side-by-side: map | legend + units, auto-sized to terminal."""
    topo = client.map_topology_id
    if topo != 3:
        print("display command only supports iso-hex topology (id=3).")
        return

    term = shutil.get_terminal_size(fallback=(160, 40))

    # Build right panel: legend, cities, units
    legend_lines = map_legend().splitlines()
    cities_lines = cities_panel_lines(client.get_cities())
    units_lines  = units_panel_lines(client.get_units())
    right_lines  = legend_lines + [""] + cities_lines + [""] + units_lines
    right_width  = max((visible_len(l) for l in right_lines), default=0)

    # Map panel gets the remaining width
    sep = " [90m|[0m "
    sep_vis = 3  # " | "
    map_cols = max(20, term.columns - right_width - sep_vis)
    map_rows = max(4, term.lines - 1)

    tiles = client.get_map()
    units = client.get_units()

    if _map_center is not None:
        cx, cy = _map_center
    else:
        cx = client.map_width  // 2
        cy = client.map_height // 2

    map_str   = render_isohex_centered(
        tiles, units, client.map_width, client.map_height,
        cx, cy, map_cols, map_rows,
    )
    map_lines = map_str.splitlines()
    map_vis_w = visible_len(map_lines[0]) if map_lines else map_cols

    height = max(len(map_lines), len(right_lines))
    rows: list[str] = []
    for i in range(height):
        ml = map_lines[i]   if i < len(map_lines)   else ""
        rl = right_lines[i] if i < len(right_lines) else ""
        rows.append(rpad(ml, map_vis_w) + sep + rl)
    print("\n".join(rows))


def cmd_help() -> None:
    print(
        "\n=== Commands ===\n"
        "  Movement & units:\n"
        "    u / units              — list your units\n"
        "    allunits               — list all visible units (own + enemy)\n"
        "    cities                 — list your cities\n"
        "    tile <x> <y>           — show tile info and units at (x,y)\n"
        "    m / move <id> <dir>    — move unit one step: N NE E SE S SW W NW\n"
        "    g / go <id> <x> <y>   — move unit to tile\n"
        "    e / end                — end your turn\n"
        "\n"
        "  Unit actions:\n"
        "    fortify <id>           — fortify unit\n"
        "    f / found <id> [name]  — found a city (settler)\n"
        "    build <id> [#]         — list/execute tile-improvement actions (worker/settler)\n"
        "    act <#> / act skip     — resolve a pending server action decision\n"
        "\n"
        "  Other:\n"
        "    poll                   — process server packets\n"
        "    topology               — show map topology and dimensions\n"
        "    display                — map + legend + units side by side (auto-sized)\n"
        "    map [x1:x2 y1:y2]     — render iso-hex map (slice in native coords)\n"
        "    map <dx> <dy>          — pan view by delta (e.g. map 2 -3)\n"
        "    map center <x> <y>    — set view centre and render\n"
        "    map legend             — show map colour/symbol legend\n"
        "    server <cmd>           — send a server command (requires hack level)\n"
        "    hack                   — check hack access level\n"
        "    h / help               — show this message\n"
        "    q / quit               — disconnect and exit\n"
    )


def cmd_move(client: FreecivClient, args: list[str]) -> None:
    """move <unit_id> <direction>   direction: N NE E SE S SW W NW"""
    # Matches freeciv enum direction8: NW=0 N=1 NE=2 W=3 E=4 SW=5 S=6 SE=7
    dirs = {"nw": 0, "n": 1, "ne": 2, "w": 3, "e": 4, "sw": 5, "s": 6, "se": 7}
    # dx,dy offsets for each direction number
    _deltas = {0: (-1,-1), 1: (0,-1), 2: (1,-1), 3: (-1,0),
               4: (1,0),  5: (-1,1), 6: (0,1),  7: (1,1)}
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
    dx, dy = _deltas[d]
    dest_tidx = client.tile_index(unit["x"] + dx, unit["y"] + dy)
    if dest_tidx < 0:
        print(f"Unit {uid}: destination is off the map.")
        return
    # Client-side feasibility check — the server suppresses its own error
    # notification when it thinks the player is watching (fresh orders +
    # moves_left > 0), so we must validate before sending.
    can_move = any(
        client.can_do_action(uid, act, dest_tidx) >= 0
        for act in (Actions.UNIT_MOVE, Actions.UNIT_MOVE2, Actions.UNIT_MOVE3)
    )
    if not can_move:
        print(f"Unit {uid} cannot move {args[1].upper()} (terrain or rules prevent it).")
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


# Worker/settler improvement actions tried in order of typical usefulness.
# Each entry: (label, [action_id, ...]) — first feasible variant wins.
_BUILD_ACTIONS: list[tuple[str, list[int]]] = [
    ("Found City",        [Actions.FOUND_CITY]),
    ("Build Road",        [Actions.ROAD, Actions.ROAD2]),
    ("Irrigate",          [Actions.IRRIGATE, Actions.IRRIGATE2]),
    ("Build Mine",        [Actions.MINE, Actions.MINE2]),
    ("Cultivate",         [Actions.CULTIVATE, Actions.CULTIVATE2]),
    ("Plant Forest",      [Actions.PLANT, Actions.PLANT2]),
    ("Transform Terrain", [Actions.TRANSFORM_TERRAIN, Actions.TRANSFORM_TERRAIN2]),
    ("Clean",             [Actions.CLEAN, Actions.CLEAN2]),
    ("Fortify",           [Actions.FORTIFY, Actions.FORTIFY2]),
]


def cmd_build(client: FreecivClient, args: list[str]) -> None:
    """build <unit_id> [choice#]  — list or execute tile-improvement actions."""
    if not args:
        print("Usage: build <unit_id> [choice#]")
        return
    try:
        uid = int(args[0])
    except ValueError:
        print(f"Invalid unit id: {args[0]}")
        return
    unit = next((u for u in client.get_units() if u["id"] == uid), None)
    if unit is None:
        print(f"Unit {uid} not found in your unit list.")
        return
    tidx = client.tile_index(unit["x"], unit["y"])

    # Build list of feasible (label, action_id) pairs
    feasible: list[tuple[str, int]] = []
    for label, action_ids in _BUILD_ACTIONS:
        for act_id in action_ids:
            if client.can_do_action(uid, act_id, tidx) >= 0:
                feasible.append((label, act_id))
                break

    if not feasible:
        print(f"Unit {uid} has no available tile-improvement actions here.")
        return

    if len(args) == 1:
        print(f"Unit {uid} ({unit['type']}) at ({unit['x']},{unit['y']}) can do:")
        for i, (label, _) in enumerate(feasible):
            print(f"  {i+1:2d}. {label}")
        print(f"  Use: build {uid} <1-{len(feasible)}>")
        return

    try:
        choice = int(args[1]) - 1
    except ValueError:
        print("Choice must be a number.")
        return
    if choice < 0 or choice >= len(feasible):
        print(f"Choice must be between 1 and {len(feasible)}.")
        return
    label, act_id = feasible[choice]
    if act_id == Actions.FOUND_CITY:
        city_name = " ".join(args[2:]) if len(args) > 2 else ""
        client.do_action(uid, act_id, tidx, name=city_name)
    else:
        client.do_action(uid, act_id, tidx)
    print(f"Unit {uid}: {label}.")


def print_action_decision(decision: dict) -> None:
    """Print a pending action decision to the REPL."""
    actor_id = decision["actor_id"]
    choices = decision["choices"]
    print(f"\n[ACTION REQUIRED] Unit {actor_id} must decide:")
    for i, c in enumerate(choices):
        prob = f"{c['min_prob'] * 100 // 200}%" if c["min_prob"] < 200 else "certain"
        print(f"  {i + 1:2d}. [{c['action_id']:3d}] {c['name']}  ({prob})")
    print(f"  Use: act <1-{len(choices)}> to choose, or: act skip to cancel\n")


def cmd_act(client: FreecivClient, args: list[str]) -> None:
    """act <choice#> | skip  — resolve a pending action decision."""
    decision = client.get_action_decision()
    if decision is None:
        print("No pending action decision.")
        return
    actor_id = decision["actor_id"]
    choices = decision["choices"]

    if not args or args[0].lower() == "skip":
        client.cancel_action_decision(actor_id)
        print(f"Action decision for unit {actor_id} cancelled.")
        return

    try:
        idx = int(args[0]) - 1
    except ValueError:
        print("Usage: act <choice number> | act skip")
        return
    if idx < 0 or idx >= len(choices):
        print(f"Choice must be between 1 and {len(choices)}.")
        return
    c = choices[idx]
    client.resolve_action_decision(actor_id, c["action_id"], c["target_id"])
    print(f"Unit {actor_id}: executed '{c['name']}'.")


async def run_cli(client: FreecivClient, stop_event: asyncio.Event) -> None:
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
            # Even on empty input, show any pending action decision.
            decision = client.get_action_decision()
            if decision:
                print_action_decision(decision)
            continue

        tokens = line.split()
        cmd = tokens[0].lower()

        if cmd in ("units", "u"):
            cmd_units(client)
        elif cmd == "allunits":
            cmd_allunits(client)
        elif cmd == "cities":
            cmd_cities(client)
        elif cmd == "tile":
            cmd_tile(client, tokens[1:])
        elif cmd in ("end", "e"):
            cmd_end(client)
        elif cmd in ("move", "m"):
            cmd_move(client, tokens[1:])
        elif cmd in ("go", "g"):
            cmd_go(client, tokens[1:])
        elif cmd == "fortify":
            cmd_fortify(client, tokens[1:])
        elif cmd in ("found", "f"):
            cmd_found(client, tokens[1:])
        elif cmd == "build":
            cmd_build(client, tokens[1:])
        elif cmd == "act":
            cmd_act(client, tokens[1:])
        elif cmd == "poll":
            alive = await client.poll(timeout=0.5)
            print(f"State: {client.state.name}, connected: {alive}")
        elif cmd == "topology":
            cmd_topology(client)
        elif cmd == "display":
            cmd_display(client)
        elif cmd == "map":
            cmd_map(client, tokens[1:])
        elif cmd == "server":
            if len(tokens) < 2:
                print("Usage: server <server command>")
            else:
                client.send_command(" ".join(tokens[1:]))
        elif cmd == "hack":
            print(f"Hack level: {'YES' if client.has_hack else 'NO'}")
        elif cmd in ("help", "h", "?"):
            cmd_help()
        elif cmd in ("quit", "exit", "q"):
            break
        else:
            print(f"Unknown command '{cmd}'. Type 'help'.")

        # After any command that may have caused a server action query,
        # show the pending decision so the user knows to respond.
        decision = client.get_action_decision()
        if decision:
            print_action_decision(decision)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Freeciv AI client")
    p.add_argument("--host", default="localhost")
    p.add_argument("--port", type=int, default=5556)
    p.add_argument("--username", default="ai-player")
    p.add_argument(
        "--data-path",
        default=None,
        help="Path to freeciv/data (auto-detected if omitted)",
    )
    p.add_argument(
        "--local",
        action="store_true",
        help="Start a local server, connect, and auto-start a game",
    )
    p.add_argument(
        "--endturn",
        type=int,
        default=0,
        help="(--local) End game after N turns (0 = unlimited)",
    )
    p.add_argument(
        "--timeout",
        type=int,
        default=0,
        help="(--local) Per-turn time limit in seconds (0 = unlimited)",
    )
    p.add_argument(
        "--verbose",
        action="store_true",
        help="Show DEBUG-level (LOG_VERBOSE) messages from the C library",
    )
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
            print(
                "\r\033[2KInterrupt — shutting down (Ctrl+C again to force).",
                flush=True,
            )
            stop_event.set()
        else:
            # Second signal: exit immediately without waiting for cleanup
            import os

            os._exit(1)

    loop.add_signal_handler(signal.SIGINT, _on_signal)
    loop.add_signal_handler(signal.SIGTERM, _on_signal)

    server: FreecivServer | None = None

    try:
        with FreecivClient(data_path=getattr(args, "data_path", None)) as client:
            if args.local:
                print(f"Starting local server on port {args.port}...")
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
            else:
                print(f"Connecting to {args.host}:{args.port} as '{args.username}'...")
                try:
                    client.connect(
                        host=args.host, port=args.port, username=args.username
                    )
                except ConnectionError as exc:
                    print(f"Error: {exc}", file=sys.stderr)
                    sys.exit(1)
                print("Connected. Waiting for game to start...")

            while not client.in_game and not stop_event.is_set():
                if client.state == ClientState.DISCONNECTED:
                    print("Disconnected before game started.", file=sys.stderr)
                    sys.exit(1)
                await asyncio.sleep(0.05)
            print("Game started!\n")

            # Auto-set map centre to geometric average of player's units
            _init_map_center(client)

            await run_cli(client, stop_event)
    finally:
        print("\nDisconnecting…")
        if server is not None:
            server.force_kill()
        await stop_log_tasks()


if __name__ == "__main__":
    asyncio.run(main())
