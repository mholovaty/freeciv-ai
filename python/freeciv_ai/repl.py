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
import sys
from typing import Any

try:
    import torch as _torch
    from freeciv_ai.torch.env import _dir_to_tile, _KNOWN_NORM, _make_action_mask
    from freeciv_ai.torch.model import ExplorerPolicy
    _TORCH_AVAILABLE = True
except ImportError:
    _torch = None  # type: ignore[assignment]
    _dir_to_tile = None  # type: ignore[assignment]
    _KNOWN_NORM = None  # type: ignore[assignment]
    _make_action_mask = None  # type: ignore[assignment]
    ExplorerPolicy = None  # type: ignore[assignment,misc]
    _TORCH_AVAILABLE = False

import signal

from freeciv_ai.map_renderer import (
    map_legend, rpad,
    render_isohex_centered,
    units_panel_lines, visible_len,
)

try:
    import readline as _readline
    _readline.parse_and_bind("Control-l: clear-screen")
except ImportError:
    pass

from freeciv_ai import FreecivClient, FreecivServer, ClientState, setup_logging
from freeciv_ai._logging import (
    start_log_tasks, stop_log_tasks, set_prompt,
    set_tui_log_callback, clear_tui_log_callback,
)
from freeciv_ai.constants import Actions, TileKnown

log = logging.getLogger("freeciv_ai.lib")

_map_center: tuple[int, int] | None = None





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
    if size <= 0:
        return round(sum(values) / len(values))
    ref = values[0]
    adjusted = []
    for v in values:
        d = (v - ref) % size
        if d > size // 2:
            d -= size
        adjusted.append(ref + d)
    return round(sum(adjusted) / len(adjusted))


def _init_map_center(client: "FreecivClient") -> None:
    """Set _map_center to the wrap-aware GUI-coord average of player units.

    We average in GUI (gui_col, gui_row) space, not MAP space, because for iso-hex
    the visual position is gui_col=(mx-my)*6 and averaging MAP x/y independently
    produces the wrong visual midpoint when units straddle the diagonal.
    """
    from freeciv_ai.map_renderer import _gui_col_wrap_period, _gui_row_wrap_period, _gui_pos
    global _map_center
    units = client.get_units()
    if not units:
        return
    topo = client.map_topology_id
    map_w = client.map_width
    map_h = client.map_height
    gui_col_wrap_period = _gui_col_wrap_period(topo, map_w)
    gui_row_wrap_period = _gui_row_wrap_period(topo, map_h)
    gui_col_vals = [_gui_pos(u["x"], u["y"], topo)[0] for u in units]
    gui_row_vals = [_gui_pos(u["x"], u["y"], topo)[1] for u in units]
    _map_center = (_wrapped_avg(gui_col_vals, gui_col_wrap_period), _wrapped_avg(gui_row_vals, gui_row_wrap_period))


def _ensure_map_center(client: "FreecivClient") -> None:
    global _map_center
    if _map_center is None and client.get_units():
        _init_map_center(client)


def _render_current_map(client: "FreecivClient", cols: int, rows: int) -> str:
    """Render map centered at _map_center, sized to cols×rows."""
    from freeciv_ai.map_renderer import _gui_pos as _map_gui_pos
    _ensure_map_center(client)
    topo = client.map_topology_id
    wrap = client.map_wrap_id
    if _map_center is not None:
        gui_col_center, gui_row_center = _map_center
    else:
        gui_col_center, gui_row_center = _map_gui_pos(client.map_width // 2, client.map_height // 2, topo)
    tiles = client.get_map()
    # Enrich tiles: tile city_name can be empty if the city-info packet hasn't
    # been processed yet but the city already appears in the player's city list.
    city_names = {c["id"]: c["name"] for c in client.get_cities() if c["name"]}
    for t in tiles:
        if t["city_id"] >= 0 and not t.get("city_name") and t["city_id"] in city_names:
            t["city_name"] = city_names[t["city_id"]]
    return render_isohex_centered(
        tiles, client.get_units(),
        client.map_width, client.map_height,
        gui_col_center, gui_row_center, cols, rows, topology_id=topo,
        wrap_x=bool(wrap & 1), wrap_y=bool(wrap & 2),
    )


def _render_display_view(client: "FreecivClient", cols: int, rows: int) -> str:
    """Render the side-by-side map | cities+units display, sized to cols×rows."""
    def _fit_lines(lines: list[str], target: int, *, center: bool) -> list[str]:
        if target <= 0:
            return []
        if len(lines) >= target:
            if center:
                start = max(0, (len(lines) - target) // 2)
                return lines[start:start + target]
            return lines[:target]
        pad = target - len(lines)
        if center:
            top = pad // 2
            return [""] * top + lines + [""] * (pad - top)
        return lines + [""] * pad

    cities_lines = cities_panel_lines(client.get_cities())
    units_lines = units_panel_lines(client.get_units())
    right_lines: list[str] = []
    for section in (cities_lines, units_lines):
        if not section:
            continue
        if right_lines:
            right_lines.append("")
        right_lines.extend(section)
    right_width = max((visible_len(l) for l in right_lines), default=0)
    sep = " \033[90m|\033[0m "
    sep_vis = 3
    map_cols = max(20, cols - right_width - sep_vis)
    map_str = _render_current_map(client, map_cols, max(4, rows - 1))
    map_lines = map_str.splitlines()
    height = max(1, rows)
    map_lines = _fit_lines(map_lines, height, center=True)
    right_lines = _fit_lines(right_lines, height, center=False)
    map_vis_w = visible_len(map_lines[0]) if map_lines else map_cols
    out = []
    for i in range(height):
        ml = map_lines[i] if i < len(map_lines) else ""
        rl = right_lines[i] if i < len(right_lines) else ""
        out.append(rpad(ml, map_vis_w) + sep + rl)
    return "\n".join(out)




def cmd_display(client: "FreecivClient") -> None:
    """display — side-by-side: map | cities + units, auto-sized to terminal."""
    term = shutil.get_terminal_size(fallback=(160, 40))
    print(_render_display_view(client, term.columns, max(4, term.lines - 1)))


def cmd_map_legend() -> None:
    """map legend — print the compact map legend to the console."""
    print(map_legend())


def cmd_map(client: "FreecivClient") -> None:
    """map — render the current centered map using the display renderer."""
    term = shutil.get_terminal_size(fallback=(160, 40))
    print(_render_current_map(client, term.columns, max(4, term.lines - 1)))


class _AIState:
    def __init__(self) -> None:
        self.policy: Any = None          # ExplorerPolicy | None
        self.ckpt: "dict | None" = None
        self.max_units: int = 16
        self.checkpoint_path: "str | None" = None
        self.trained_episode: "int | None" = None
        self.hidden_size: "int | None" = None
        self.obs_size: "int | None" = None


def _build_policy(ai: _AIState, map_w: int, map_h: int) -> None:
    """Construct ExplorerPolicy from staged checkpoint using known map dims."""
    assert _TORCH_AVAILABLE and _torch is not None and ExplorerPolicy is not None
    assert ai.ckpt is not None and ai.hidden_size is not None
    obs_size = map_w * map_h + ai.max_units * 3
    policy = ExplorerPolicy(obs_size=obs_size, max_units=ai.max_units, hidden_size=ai.hidden_size)
    policy.load_state_dict(ai.ckpt["model"])
    policy.eval()
    ai.policy = policy
    ai.obs_size = obs_size


def _make_obs_for_client(client: "FreecivClient", max_units: int, units: list) -> object:
    """Build the flat float32 observation tensor from the current game state."""
    assert _TORCH_AVAILABLE and _torch is not None and _KNOWN_NORM is not None
    w, h = client.map_width, client.map_height
    map_vec = _torch.zeros(w * h, dtype=_torch.float32)
    for t in client.get_map():
        idx = t["index"]
        if 0 <= idx < w * h:
            map_vec[idx] = _KNOWN_NORM.get(t["known"], 0.0)
    unit_vec = _torch.zeros(max_units * 3, dtype=_torch.float32)
    for i, u in enumerate(units):
        base = i * 3
        unit_vec[base]     = u["x"] / max(w, 1)
        unit_vec[base + 1] = u["y"] / max(h, 1)
        moves_max = u["moves_max"] or 1
        unit_vec[base + 2] = u["moves_left"] / moves_max
    return _torch.cat([map_vec, unit_vec])


def cmd_ai_load(client: "FreecivClient", ai: _AIState, args: list) -> None:
    if not _TORCH_AVAILABLE:
        print("torch is not installed — cannot load AI model.")
        return
    if not args:
        print("Usage: ai load <path>")
        return
    assert _torch is not None
    path = args[0]
    try:
        ckpt = _torch.load(path, weights_only=True)
    except Exception as exc:
        print(f"Failed to load checkpoint: {exc}")
        return

    try:
        hidden_size = ckpt["model"]["trunk.0.weight"].shape[0]
    except (KeyError, IndexError) as exc:
        print(f"Cannot infer hidden_size from checkpoint: {exc}")
        return

    ai.ckpt = ckpt
    ai.hidden_size = hidden_size
    ai.checkpoint_path = path
    ai.trained_episode = ckpt.get("episode")
    ai.policy = None  # will be built once map dims are known

    if client.in_game:
        _build_policy(ai, client.map_width, client.map_height)
        ep_str = f"ep {ai.trained_episode}" if ai.trained_episode is not None else "ep ?"
        print(
            f"AI loaded: obs_size={ai.obs_size}  hidden={hidden_size}"
            f"  max_units={ai.max_units}  ({ep_str})"
        )
    else:
        print("AI checkpoint staged — model will be built when game starts.")


def _try_move(client: "FreecivClient", uid: int, tidx: int) -> "int | None":
    """Try UNIT_MOVE, UNIT_MOVE2, UNIT_MOVE3. Return action id used, or None if all blocked."""
    for act in (Actions.UNIT_MOVE, Actions.UNIT_MOVE2, Actions.UNIT_MOVE3):
        if client.can_do_action(uid, act, tidx) >= 0:
            client.do_action(uid, act, tidx)
            return act
    return None


def cmd_ai_turn(client: "FreecivClient", ai: _AIState) -> None:
    if ai.ckpt is None:
        print("No model loaded — run: ai load <path>")
        return
    if not client.can_act:
        print("Not your turn.")
        return

    if ai.policy is None:
        # Deferred build now that we're in game
        _build_policy(ai, client.map_width, client.map_height)
        ep_str = f"ep {ai.trained_episode}" if ai.trained_episode is not None else "ep ?"
        print(
            f"AI model built: obs_size={ai.obs_size}  hidden={ai.hidden_size}"
            f"  max_units={ai.max_units}  ({ep_str})"
        )

    assert ai.policy is not None and _torch is not None and _dir_to_tile is not None

    # Establish stable unit ordering (indices used for policy head alignment)
    all_units = client.get_units()[: ai.max_units]
    if not all_units:
        print("No units to move.")
        return

    n_units = len(all_units)
    uid_to_idx = {u["id"]: i for i, u in enumerate(all_units)}
    active: set[int] = {u["id"] for u in all_units}

    total_moves = total_blocked = total_skips = 0
    dir_names = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]

    while active:
        # Refresh unit states so moves_left / positions are current
        current_units = {u["id"]: u for u in client.get_units()[: ai.max_units]}

        # Build obs from refreshed snapshot, preserving original slot order
        obs_units = [current_units.get(u["id"], u) for u in all_units]
        obs = _make_obs_for_client(client, ai.max_units, obs_units)
        mask = _make_action_mask(client, obs_units, ai.max_units)  # type: ignore[misc]

        with _torch.no_grad():  # type: ignore[union-attr]
            actions, _ = ai.policy.select_actions(obs, n_units, mask)

        did_anything = False
        to_remove: set[int] = set()

        for uid in list(active):
            unit = current_units.get(uid)
            if unit is None:
                to_remove.add(uid)
                continue
            idx = uid_to_idx[uid]
            act = actions[idx]
            x, y = unit["x"], unit["y"]

            if act == 0:
                print(f"  unit {uid} @ ({x},{y}) → skip")
                total_skips += 1
                to_remove.add(uid)
                continue

            direction = act - 1
            tx, ty = _dir_to_tile(x, y, direction)  # type: ignore[misc]
            tidx = client.tile_index(tx, ty)
            dir_name = dir_names[direction]

            if tidx < 0:
                print(f"  unit {uid} @ ({x},{y}) → {dir_name} off-map")
                total_blocked += 1
                to_remove.add(uid)
                continue

            used = _try_move(client, uid, tidx)
            if used is not None:
                print(f"  unit {uid} @ ({x},{y}) → {dir_name} ({tx},{ty})")
                total_moves += 1
                did_anything = True
            else:
                print(f"  unit {uid} @ ({x},{y}) → {dir_name} blocked")
                total_blocked += 1
                to_remove.add(uid)

        active -= to_remove

        if not did_anything:
            break  # safety: nothing moved, avoid infinite loop

        # Remove units that have exhausted their movement points
        refreshed = {u["id"]: u for u in client.get_units()[: ai.max_units]}
        active = {uid for uid in active if refreshed.get(uid, {}).get("moves_left", 0) > 0}

    print(f"AI done — {total_moves} moves, {total_blocked} blocked, {total_skips} skipped")


def cmd_ai_status(ai: _AIState) -> None:
    if ai.ckpt is None:
        print("No model loaded.")
        return
    ep_str = str(ai.trained_episode) if ai.trained_episode is not None else "?"
    built = "yes" if ai.policy is not None else "no (staged, awaiting game start)"
    print(
        f"AI status:\n"
        f"  path       : {ai.checkpoint_path}\n"
        f"  episode    : {ep_str}\n"
        f"  obs_size   : {ai.obs_size if ai.obs_size is not None else '(pending)'}\n"
        f"  hidden     : {ai.hidden_size}\n"
        f"  max_units  : {ai.max_units}\n"
        f"  model built: {built}"
    )


def cmd_ai(client: "FreecivClient", ai: _AIState, args: list) -> None:
    sub = args[0] if args else ""
    if sub == "load":
        cmd_ai_load(client, ai, args[1:])
    elif sub in ("turn", "t"):
        cmd_ai_turn(client, ai)
    elif sub == "status":
        cmd_ai_status(ai)
    else:
        print("Usage: ai <load <path> | turn | status>")


def cmd_help() -> None:
    print(
        "\n=== Commands ===\n"
        "  Movement & units:\n"
        "    u / units              — list your units\n"
        "    allunits               — list all visible units (own + enemy)\n"
        "    cities                 — list your cities\n"
        "    tile <x> <y>           — show tile info and units at (x,y)\n"
        "    m / move <id> <dir>    — move unit one step (valid dirs depend on topology)\n"
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
        "    display                — map + cities + units side by side (auto-sized)\n"
        "    map                    — render the current centered map\n"
        "    map legend             — print the compact map colour/symbol legend\n"
        "    server <cmd>           — send a server command (requires hack level)\n"
        "    hack                   — check hack access level\n"
        "    h / help               — show this message\n"
        "    q / quit               — disconnect and exit\n"
        "\n"
        "  AI:\n"
        "    ai load <path>         — load checkpoint (.pt); game must be running\n"
        "    ai turn / ai t         — AI takes this turn: moves all units, ends turn\n"
        "    ai status              — show loaded model info\n"
    )


def cmd_move(client: FreecivClient, args: list[str]) -> None:
    """move <unit_id> <direction>   direction: N NE E SE S SW W NW"""
    # Matches freeciv enum direction8: NW=0 N=1 NE=2 W=3 E=4 SW=5 S=6 SE=7
    dirs = {"nw": 0, "n": 1, "ne": 2, "w": 3, "e": 4, "sw": 5, "s": 6, "se": 7}
    valid_dirs = ["N", "E", "S", "W", "NE", "SE", "SW", "NW"]
    if client.map_topology_id == 2:
        valid_dirs = ["N", "NE", "E", "S", "SW", "W"]
    elif client.map_topology_id == 3:
        valid_dirs = ["NW", "N", "E", "SE", "S", "W"]
    valid_dir_set = {name.lower() for name in valid_dirs}
    valid_dir_text = " ".join(valid_dirs)
    # dx,dy offsets for each direction number
    _deltas = {0: (-1,-1), 1: (0,-1), 2: (1,-1), 3: (-1,0),
               4: (1,0),  5: (-1,1), 6: (0,1),  7: (1,1)}
    if len(args) != 2:
        print(f"Usage: move <unit_id> <{'|'.join(valid_dirs)}>")
        return
    dir_name = args[1].lower()
    d = dirs.get(dir_name)
    if d is None:
        print(f"Unknown direction '{args[1]}'. Use: {valid_dir_text}")
        return
    if dir_name not in valid_dir_set:
        print(f"Direction {args[1].upper()} is invalid on this topology. Use: {valid_dir_text}")
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
        print(f"Unit {uid} cannot move {args[1].upper()} (terrain, zone of control, or rules prevent it).")
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
    if city_name:
        client.do_action(uid, Actions.FOUND_CITY, tidx, name=city_name)
    else:
        client.request_city_name_suggestion(uid)


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
        if city_name:
            client.do_action(uid, act_id, tidx, name=city_name)
        else:
            client.request_city_name_suggestion(uid)
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


async def _dispatch_command(
    client: FreecivClient,
    _ai: "_AIState",
    line: str,
    tui=None,  # FreecivTUI | None
) -> bool:
    """Dispatch one command line. Returns False if the user wants to quit."""
    _tui = tui  # FreecivTUI | None — duck typed, no hard import needed
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
        await client.poll(timeout=1.5)   # pick up city-creation packets
    elif cmd == "build":
        cmd_build(client, tokens[1:])
        await client.poll(timeout=1.5)   # pick up city-creation packets if FOUND_CITY
    elif cmd == "act":
        cmd_act(client, tokens[1:])
    elif cmd == "poll":
        alive = await client.poll(timeout=0.5)
        print(f"State: {client.state.name}, connected: {alive}")
    elif cmd == "topology":
        cmd_topology(client)
    elif cmd == "display":
        if _tui is not None:
            _tui._view_mode = "display"
            term = shutil.get_terminal_size(fallback=(80, 24))
            map_rows = max(4, int(term.lines * 2 / 3))
            _tui.update_map(_render_display_view(client, term.columns, map_rows))
        else:
            cmd_display(client)
    elif cmd == "map":
        if len(tokens) == 1:
            if _tui is not None:
                _tui._view_mode = "map"
                term = shutil.get_terminal_size(fallback=(80, 24))
                map_rows = max(4, int(term.lines * 2 / 3))
                _tui.update_map(_render_current_map(client, term.columns, map_rows))
            else:
                cmd_map(client)
        elif len(tokens) == 2 and tokens[1].lower() == "legend":
            cmd_map_legend()
        else:
            print("Usage: map | map legend")
    elif cmd == "server":
        if len(tokens) < 2:
            print("Usage: server <server command>")
        else:
            client.send_command(" ".join(tokens[1:]))
    elif cmd == "hack":
        print(f"Hack level: {'YES' if client.has_hack else 'NO'}")
    elif cmd == "ai":
        cmd_ai(client, _ai, tokens[1:])
    elif cmd in ("help", "h", "?"):
        cmd_help()
    elif cmd in ("quit", "exit", "q"):
        return False
    else:
        print(f"Unknown command '{cmd}'. Type 'help'.")

    # After any command that may have caused a server action query,
    # show the pending decision so the user knows to respond.
    decision = client.get_action_decision()
    if decision:
        print_action_decision(decision)

    return True


async def run_cli(client: FreecivClient, stop_event: asyncio.Event) -> None:
    cmd_help()
    _ai = _AIState()

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
            decision = client.get_action_decision()
            if decision:
                print_action_decision(decision)
            continue

        if not await _dispatch_command(client, _ai, line):
            break


class _TuiStdout:
    """Redirect sys.stdout to the TUI log pane in TUI mode."""

    def __init__(self, tui) -> None:  # type: ignore[type-arg]
        self._tui = tui  # FreecivTUI — duck typed
        self._buf = ""

    def write(self, s: str) -> int:
        self._buf += s
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            self._tui.append_log(line)
        return len(s)

    def flush(self) -> None:
        if self._buf:
            self._tui.append_log(self._buf)
            self._buf = ""

    def fileno(self) -> int:
        raise OSError("_TuiStdout has no fileno")


async def _run_tui_mode(
    client: FreecivClient,
    stop_event: asyncio.Event,
) -> None:
    """Run the split-screen TUI REPL."""
    try:
        from freeciv_ai.tui import FreecivTUI  # type: ignore[import]
    except ImportError:
        print(
            "prompt_toolkit not installed — falling back to classic REPL.\n"
            "Install with: pip install prompt_toolkit"
        )
        await run_cli(client, stop_event)
        return

    def _get_prompt() -> str:
        if client.state == ClientState.RUNNING:
            t = f"[Turn {client.turn}"
            t += ", your turn" if client.can_act else ""
            t += "] "
            return f"{t}> "
        return "> "

    tui = FreecivTUI(get_prompt_fn=_get_prompt)

    # Route all logging output into the TUI log pane.
    set_tui_log_callback(tui.append_log)
    # Redirect print() output into the TUI log pane.
    real_stdout = sys.stdout
    sys.stdout = _TuiStdout(tui)  # type: ignore[assignment]

    try:
        # Render the initial display view.
        term = shutil.get_terminal_size(fallback=(80, 24))
        map_rows = max(4, int(term.lines * 2 / 3))
        tui.update_map(_render_display_view(client, term.columns, map_rows))

        _ai = _AIState()

        async def _map_refresh_task() -> None:
            while not stop_event.is_set():
                await asyncio.sleep(1.0)
                if client.in_game:
                    _term = shutil.get_terminal_size(fallback=(80, 24))
                    _rows = max(4, int(_term.lines * 2 / 3))
                    try:
                        if tui._view_mode == "display":
                            content = _render_display_view(client, _term.columns, _rows)
                        else:
                            content = _render_current_map(client, _term.columns, _rows)
                        tui.update_map(content)
                    except Exception:
                        pass

        async def _cli_task() -> None:
            tui._pending_command = None
            while not stop_event.is_set():
                while tui._pending_command is None and not stop_event.is_set():
                    await asyncio.sleep(0.05)
                if tui._pending_command is None:
                    break
                line = tui._pending_command.strip()
                tui._pending_command = None
                if line:
                    should_continue = await _dispatch_command(client, _ai, line, tui=tui)
                    if not should_continue:
                        tui.app.exit()
                        stop_event.set()
                        break

        async def _watch_stop() -> None:
            """Exit the TUI app when stop_event fires externally (e.g. SIGINT)."""
            await stop_event.wait()
            if tui.app.is_running:
                tui.app.exit()

        map_task = asyncio.create_task(_map_refresh_task())
        cli_task = asyncio.create_task(_cli_task())
        watch_task = asyncio.create_task(_watch_stop())

        try:
            await tui.run_async()
        finally:
            stop_event.set()
            for t in (map_task, cli_task, watch_task):
                t.cancel()
            for t in (map_task, cli_task, watch_task):
                try:
                    await t
                except (asyncio.CancelledError, Exception):
                    pass
    finally:
        sys.stdout = real_stdout  # type: ignore[assignment]
        clear_tui_log_callback()


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
    p.add_argument(
        "--no-tui",
        dest="tui",
        action="store_false",
        default=True,
        help="Disable the split-screen TUI and use the classic readline REPL",
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

            # in_game flips on the game-start packet, but tile visibility
            # packets arrive shortly after (and on reconnect the server must
            # resend the full map state).  Wait until at least one tile is
            # currently visible before handing control to the REPL.
            for _ in range(100):  # up to ~5 s
                if any(t["known"] == 2 for t in client.get_map()):
                    break
                await asyncio.sleep(0.05)

            # Starting units may arrive a little after the first visible-tile
            # packets. Give them a short chance to land before the first render.
            for _ in range(40):  # up to ~2 s
                if client.get_units():
                    break
                await asyncio.sleep(0.05)

            print("Game started!\n")

            # Auto-set map centre to geometric average of player's units
            _init_map_center(client)

            if args.tui:
                await _run_tui_mode(client, stop_event)
            else:
                await run_cli(client, stop_event)
    finally:
        print("\nDisconnecting…")
        if server is not None:
            server.force_kill()
        await stop_log_tasks()


if __name__ == "__main__":
    asyncio.run(main())
