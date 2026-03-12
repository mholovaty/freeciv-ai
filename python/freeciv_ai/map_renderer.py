"""Freeciv map renderer — supports all 4 topology modes.

Topology IDs (bitmask: TF_ISO=1, TF_HEX=2):
  0  flat square  — simple rectangular grid
  1  iso square   — isometric diamond view
  2  flat hex     — column-staggered hex grid (odd columns shifted down)
  3  iso-hex      — isometric hex, aligned with Freeciv client projection

Center coords passed to render_map_centered() are GUI coords.
"""

import re

# ---------------------------------------------------------------------------
# 24-bit RGB colour helpers
# ---------------------------------------------------------------------------

Color = tuple[int, int, int]  # (R, G, B) each 0-255


def _bg(c: Color) -> str:
    return f"\033[48;2;{c[0]};{c[1]};{c[2]}m"


def _fg(c: Color) -> str:
    return f"\033[38;2;{c[0]};{c[1]};{c[2]}m"


MAP_RESET = "\033[0m"


def _map_bg(c: Color) -> str:
    return _bg(c)


def _map_fg(c: Color) -> str:
    return _fg(c)


# ---------------------------------------------------------------------------
# Terrain palette
# ---------------------------------------------------------------------------

_TERRAIN_BG: dict[str, Color] = {
    "ocean": (0, 80, 180),
    "deep ocean": (0, 50, 130),
    "lake": (30, 120, 200),
    "coast": (70, 160, 220),
    "grassland": (55, 160, 45),
    "plains": (185, 175, 70),
    "desert": (215, 195, 75),
    "mountains": (120, 110, 100),
    "hills": (145, 100, 55),
    "forest": (25, 105, 35),
    "jungle": (15, 135, 50),
    "tundra": (140, 165, 195),
    "arctic": (210, 230, 255),
    "glacier": (210, 230, 255),
    "swamp": (50, 95, 65),
    "inaccessible": (5, 5, 5),
}

BG_UNKNOWN: Color = (12, 12, 12)
BG_FOGGED: Color = (32, 30, 28)
BG_DEFAULT: Color = (90, 90, 90)
FG_CONTENT: Color = (255, 255, 255)
FG_BORDER: Color = (50, 45, 35)
FG_BORDER_VISIBLE = FG_BORDER

# Foreground colors for notable tile objects
FG_CITY: Color = (255, 220, 50)  # gold
FG_OWN_UNIT: Color = (120, 230, 255)  # light cyan
FG_ENEMY: Color = (255, 110, 80)  # orange-red


def terrain_bg(terrain: str) -> Color:
    return _TERRAIN_BG.get(terrain.lower(), BG_DEFAULT)


# ---------------------------------------------------------------------------
# Canvas
# ---------------------------------------------------------------------------

_NO_COLOR: Color = (-1, -1, -1)


class MapCanvas:
    """Fixed-size character + colour canvas."""

    def __init__(self, cols: int, rows: int) -> None:
        self.cols = cols
        self.rows = rows
        self._ch: list[list[str]] = [[" "] * cols for _ in range(rows)]
        self._fg: list[list[Color]] = [[_NO_COLOR] * cols for _ in range(rows)]
        self._bg: list[list[Color]] = [[_NO_COLOR] * cols for _ in range(rows)]

    def put(
        self, col: int, row: int, ch: str, fg: Color = FG_CONTENT, bg: Color = _NO_COLOR
    ) -> None:
        if 0 <= col < self.cols and 0 <= row < self.rows:
            self._ch[row][col] = ch
            self._fg[row][col] = fg
            self._bg[row][col] = bg

    def render(self) -> str:
        lines: list[str] = []
        for row in range(self.rows):
            parts: list[str] = []
            cur_fg = cur_bg = _NO_COLOR
            for col in range(self.cols):
                ch = self._ch[row][col]
                fg = self._fg[row][col]
                bg = self._bg[row][col]
                esc = ""
                if fg != cur_fg:
                    esc += _fg(fg) if fg != _NO_COLOR else "\033[39m"
                    cur_fg = fg
                if bg != cur_bg:
                    esc += _bg(bg) if bg != _NO_COLOR else "\033[49m"
                    cur_bg = bg
                parts.append(esc + ch)
            lines.append("".join(parts) + MAP_RESET)
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Coordinate helpers
# ---------------------------------------------------------------------------


def _gui_pos(mx: int, my: int, topo: int) -> tuple[int, int]:
    """Return (gui_col, gui_row) for MAP tile (mx, my) under topology topo."""
    if topo == 0:  # flat-square
        return mx * 7, my * 3
    if topo == 1:  # iso-square
        return (mx - my) * 7, (mx + my) * 3
    if topo == 2:  # flat-hex: odd columns shifted down by 2
        return mx * 6, my * 4 + (mx % 2) * 2
    if topo == 3:  # iso-hex: Freeciv map_to_gui_vector() with 6x2 steps
        return (mx - my) * 6, (mx + my) * 2
    else:
        raise AssertionError()


def _gui_col_wrap_period(topo: int, map_width: int) -> int:
    """GUI-column delta for one full x-wrap.

    For isometric maps, Freeciv wraps in native coordinates. In map coordinates
    the x-wrap vector is (map_width, -map_width), which is a pure horizontal
    shift in GUI space.
    """
    if topo == 3:
        return 12 * map_width  # (mx, my) -> (mx+W, my-W)
    if topo == 2:
        return 6 * map_width  # gui_col = mx*6, step 6
    if topo == 1:
        return 14 * map_width  # (mx, my) -> (mx+W, my-W)
    return 7 * map_width  # gui_col = mx*7, step 7


def _gui_row_wrap_period(topo: int, map_height: int) -> int:
    """GUI-row delta for one full y-wrap.

    For isometric maps, the y-wrap vector in map coordinates is
    (map_height / 2, map_height / 2), which is a pure vertical GUI shift.
    """
    if topo == 3:
        return 2 * map_height  # (mx, my) -> (mx+H/2, my+H/2)
    if topo == 2:
        return 4 * map_height  # gui_row = my*4 + (mx%2)*2, my contributes step 4
    return 3 * map_height  # topo 0: (mx, my+H), topo 1: (mx+H/2, my+H/2)


# Keep for backward compat (repl.py imports this)
def map_pos_to_native(mx: int, my: int, map_width: int) -> tuple[int, int]:
    nat_y = mx + my - map_width
    nat_x = (2 * mx - nat_y - (nat_y & 1)) // 2
    return nat_x, nat_y


# ---------------------------------------------------------------------------
# Cell drawing
# ---------------------------------------------------------------------------


def _tile_unit_slots(
    own_types: list[str], n_foreign: int, n_slots: int = 3
) -> list[tuple[str, Color]]:
    """Fill *n_slots* unit display slots: own (cyan) first, then enemy (orange).

    Each own unit occupies one slot as the first letter of its type name.
    If more own units exist than slots allow, the last own slot shows a count.
    Enemy units take the remaining slot(s) as 'u' or a count.
    """
    n_own = len(own_types)
    # Reserve one slot for enemy if both sides present
    max_own = (n_slots - 1) if (n_foreign > 0 and n_own > 0) else n_slots
    shown_own = min(n_own, max_own)

    slots: list[tuple[str, Color]] = [
        (t[0].upper(), FG_OWN_UNIT) for t in own_types[:shown_own]
    ]
    # Replace last own slot with count if overflow
    if n_own > shown_own and shown_own > 0:
        slots[-1] = (str(n_own) if n_own <= 9 else "+", FG_OWN_UNIT)

    # Enemy indicator
    if n_foreign > 0:
        c = "u" if n_foreign == 1 else (str(n_foreign) if n_foreign <= 9 else "+")
        slots.append((c, FG_ENEMY))

    while len(slots) < n_slots:
        slots.append((" ", FG_CONTENT))
    return slots[:n_slots]


def _tile_cells(
    tile: dict, own_units_map: dict
) -> tuple[str, Color, str, Color, str, Color, str, Color]:
    """Return (tl_ch, tl_fg, tr_ch, tr_fg, bl_ch, bl_fg, br_ch, br_fg).

    TL (top-left)  = city initial (gold) or space
    TR, BL, BR     = unit slots — own (cyan), enemy (orange-red)
    """
    city_id = tile.get("city_id", -1)
    n_units = tile.get("n_units", 0)
    key = (tile["x"], tile["y"])
    own_types = own_units_map.get(key, [])
    n_foreign = max(0, n_units - len(own_types))

    if city_id >= 0:
        name = (tile.get("city_name") or "").strip()
        tl: tuple[str, Color] = (name[0].upper() if name else "*", FG_CITY)
    else:
        tl = (" ", FG_CONTENT)

    tr, bl, br = _tile_unit_slots(own_types, n_foreign, n_slots=3)
    return tl[0], tl[1], tr[0], tr[1], bl[0], bl[1], br[0], br[1]


def _cell_colors(
    tile: dict | None, own_units_map: dict
) -> tuple[Color, str, Color, str, Color, str, Color, str, Color, Color]:
    """Returns (bg, tl_ch, tl_fg, tr_ch, tr_fg, bl_ch, bl_fg, br_ch, br_fg, border)."""
    _empty = (" ", FG_CONTENT, " ", FG_CONTENT, " ", FG_CONTENT, " ", FG_CONTENT)
    if tile is None:
        return BG_UNKNOWN, *_empty, FG_BORDER
    known = tile["known"]
    if known == 0:
        return BG_UNKNOWN, *_empty, FG_BORDER
    bg = terrain_bg(tile.get("terrain") or "")
    if known == 2:
        cells = _tile_cells(tile, own_units_map)
        return bg, *cells, FG_BORDER_VISIBLE
    return bg, *_empty, FG_BORDER


def _draw_hex_cell(
    canvas: MapCanvas,
    canvas_col: int,
    canvas_row: int,
    bg: Color,
    tl_ch: str,
    tl_fg: Color,
    tr_ch: str,
    tr_fg: Color,
    bl_ch: str,
    bl_fg: Color,
    br_ch: str,
    br_fg: Color,
    border: Color = FG_BORDER,
) -> None:
    """Draw a hex cell — 8 chars wide, 4 rows tall, step 6.

    canvas_col+0 and canvas_col+7 are shared border cols with the left/right neighbours
    (next cell overwrites them), so the effective advance per column is 6.

        /   \
       / 1 2 \
       \ 3 4 /
        \   /

    """
    N = _NO_COLOR
    # row 0: top indent (/ and \ sit one column inward)
    # canvas.put(canvas_col, canvas_row, " ", fg=FG_CONTENT, bg=N)
    canvas.put(canvas_col + 1, canvas_row, "/", fg=border, bg=N)
    canvas.put(canvas_col + 2, canvas_row, " ", fg=FG_CONTENT, bg=bg)
    canvas.put(canvas_col + 3, canvas_row, " ", fg=FG_CONTENT, bg=bg)
    canvas.put(canvas_col + 4, canvas_row, " ", fg=FG_CONTENT, bg=bg)
    canvas.put(canvas_col + 5, canvas_row, " ", fg=FG_CONTENT, bg=bg)
    canvas.put(canvas_col + 6, canvas_row, "\\", fg=border, bg=N)
    # canvas.put(canvas_col + 7, canvas_row, " ", fg=FG_CONTENT, bg=N)
    # row 1: top content row (/ and \ flush at edges)
    canvas.put(canvas_col, canvas_row + 1, "/", fg=border, bg=N)
    canvas.put(canvas_col + 1, canvas_row + 1, " ", fg=FG_CONTENT, bg=bg)
    canvas.put(canvas_col + 2, canvas_row + 1, tl_ch, fg=tl_fg, bg=bg)
    canvas.put(canvas_col + 3, canvas_row + 1, " ", fg=FG_CONTENT, bg=bg)
    canvas.put(canvas_col + 4, canvas_row + 1, " ", fg=FG_CONTENT, bg=bg)
    canvas.put(canvas_col + 5, canvas_row + 1, tr_ch, fg=tr_fg, bg=bg)
    canvas.put(canvas_col + 6, canvas_row + 1, " ", fg=FG_CONTENT, bg=bg)
    canvas.put(canvas_col + 7, canvas_row + 1, "\\", fg=border, bg=N)
    # row 2: bottom content row (\ and / flush at edges)
    canvas.put(canvas_col, canvas_row + 2, "\\", fg=border, bg=N)
    canvas.put(canvas_col + 1, canvas_row + 2, " ", fg=FG_CONTENT, bg=bg)
    canvas.put(canvas_col + 2, canvas_row + 2, bl_ch, fg=bl_fg, bg=bg)
    canvas.put(canvas_col + 3, canvas_row + 2, " ", fg=FG_CONTENT, bg=bg)
    canvas.put(canvas_col + 4, canvas_row + 2, " ", fg=FG_CONTENT, bg=bg)
    canvas.put(canvas_col + 5, canvas_row + 2, br_ch, fg=br_fg, bg=bg)
    canvas.put(canvas_col + 6, canvas_row + 2, " ", fg=FG_CONTENT, bg=bg)
    canvas.put(canvas_col + 7, canvas_row + 2, "/", fg=border, bg=N)
    # row 3: bottom indent (\ and / sit one column inward)
    # canvas.put(canvas_col, canvas_row + 3, " ", fg=FG_CONTENT, bg=N)
    canvas.put(canvas_col + 1, canvas_row + 3, "\\", fg=border, bg=N)
    canvas.put(canvas_col + 2, canvas_row + 3, " ", fg=FG_CONTENT, bg=bg)
    canvas.put(canvas_col + 3, canvas_row + 3, " ", fg=FG_CONTENT, bg=bg)
    canvas.put(canvas_col + 4, canvas_row + 3, " ", fg=FG_CONTENT, bg=bg)
    canvas.put(canvas_col + 5, canvas_row + 3, " ", fg=FG_CONTENT, bg=bg)
    canvas.put(canvas_col + 6, canvas_row + 3, "/", fg=border, bg=N)
    # canvas.put(canvas_col + 7, canvas_row + 3, " ", fg=FG_CONTENT, bg=N)


def _draw_square_cell(
    canvas: MapCanvas,
    canvas_col: int,
    canvas_row: int,
    bg: Color,
    tl_ch: str,
    tl_fg: Color,
    tr_ch: str,
    tr_fg: Color,
    bl_ch: str,
    bl_fg: Color,
    br_ch: str,
    br_fg: Color,
    border: Color = FG_BORDER,
) -> None:
    """Draw a square cell — 8 chars wide, 4 rows tall.

        +------+
        | TL TR|
        | BL BR|
        +------+

    Content at cols 2 and 5 (same positions as hex cell).
    """
    N = _NO_COLOR
    # row 0: top border
    canvas.put(canvas_col, canvas_row, "+", fg=border, bg=N)
    canvas.put(canvas_col + 1, canvas_row, "-", fg=border, bg=N)
    canvas.put(canvas_col + 2, canvas_row, "-", fg=border, bg=N)
    canvas.put(canvas_col + 3, canvas_row, "-", fg=border, bg=N)
    canvas.put(canvas_col + 4, canvas_row, "-", fg=border, bg=N)
    canvas.put(canvas_col + 5, canvas_row, "-", fg=border, bg=N)
    canvas.put(canvas_col + 6, canvas_row, "-", fg=border, bg=N)
    canvas.put(canvas_col + 7, canvas_row, "+", fg=border, bg=N)
    # row 1: top content row
    canvas.put(canvas_col, canvas_row + 1, "|", fg=border, bg=N)
    canvas.put(canvas_col + 1, canvas_row + 1, " ", fg=FG_CONTENT, bg=bg)
    canvas.put(canvas_col + 2, canvas_row + 1, tl_ch, fg=tl_fg, bg=bg)
    canvas.put(canvas_col + 3, canvas_row + 1, " ", fg=FG_CONTENT, bg=bg)
    canvas.put(canvas_col + 4, canvas_row + 1, " ", fg=FG_CONTENT, bg=bg)
    canvas.put(canvas_col + 5, canvas_row + 1, tr_ch, fg=tr_fg, bg=bg)
    canvas.put(canvas_col + 6, canvas_row + 1, " ", fg=FG_CONTENT, bg=bg)
    canvas.put(canvas_col + 7, canvas_row + 1, "|", fg=border, bg=N)
    # row 2: bottom content row
    canvas.put(canvas_col, canvas_row + 2, "|", fg=border, bg=N)
    canvas.put(canvas_col + 1, canvas_row + 2, " ", fg=FG_CONTENT, bg=bg)
    canvas.put(canvas_col + 2, canvas_row + 2, bl_ch, fg=bl_fg, bg=bg)
    canvas.put(canvas_col + 3, canvas_row + 2, " ", fg=FG_CONTENT, bg=bg)
    canvas.put(canvas_col + 4, canvas_row + 2, " ", fg=FG_CONTENT, bg=bg)
    canvas.put(canvas_col + 5, canvas_row + 2, br_ch, fg=br_fg, bg=bg)
    canvas.put(canvas_col + 6, canvas_row + 2, " ", fg=FG_CONTENT, bg=bg)
    canvas.put(canvas_col + 7, canvas_row + 2, "|", fg=border, bg=N)
    # row 3: bottom border
    canvas.put(canvas_col, canvas_row + 3, "+", fg=border, bg=N)
    canvas.put(canvas_col + 1, canvas_row + 3, "-", fg=border, bg=N)
    canvas.put(canvas_col + 2, canvas_row + 3, "-", fg=border, bg=N)
    canvas.put(canvas_col + 3, canvas_row + 3, "-", fg=border, bg=N)
    canvas.put(canvas_col + 4, canvas_row + 3, "-", fg=border, bg=N)
    canvas.put(canvas_col + 5, canvas_row + 3, "-", fg=border, bg=N)
    canvas.put(canvas_col + 6, canvas_row + 3, "-", fg=border, bg=N)
    canvas.put(canvas_col + 7, canvas_row + 3, "+", fg=border, bg=N)


# ---------------------------------------------------------------------------
# Pure coordinate helpers
# ---------------------------------------------------------------------------


def _nearest(base: int, ctr: int, period: int) -> int:
    """Shift base by a multiple of period to land closest to ctr."""
    d = (base - ctr) % period
    if d > period // 2:
        d -= period
    return ctr + d


def _tile_layout(
    tiles: list[dict],
    map_width: int,
    map_height: int,
    topology_id: int,
    gui_col_center: int,
    gui_row_center: int,
    viewport_cols: int,
    viewport_rows: int,
    wrap_x: bool = True,
    wrap_y: bool = False,
) -> dict[tuple[int, int], tuple[int, int]]:
    """Pure coordinate mapping. Returns {(mx, my): (canvas_col, canvas_row)}
    for every tile that falls inside the viewport. No drawing.
    """
    gui_col_wrap_period = _gui_col_wrap_period(topology_id, map_width)
    gui_row_wrap_period = _gui_row_wrap_period(topology_id, map_height)
    gui_col_tile_step = 6 if topology_id in (2, 3) else 7
    cell_half_width, cell_half_height = 4, 2
    gui_col_viewport_origin = gui_col_center + cell_half_width - viewport_cols // 2
    gui_row_viewport_origin = gui_row_center + cell_half_height - viewport_rows // 2
    gui_col_lo, gui_col_hi = (
        gui_col_viewport_origin - gui_col_tile_step,
        gui_col_viewport_origin + viewport_cols,
    )
    gui_row_lo, gui_row_hi = (
        gui_row_viewport_origin - cell_half_height,
        gui_row_viewport_origin + viewport_rows,
    )

    result: dict[tuple[int, int], tuple[int, int]] = {}
    for t in tiles:
        mx, my = t["x"], t["y"]
        gui_col_base, gui_row_base = _gui_pos(mx, my, topology_id)
        gui_col, gui_row = gui_col_base, gui_row_base

        if wrap_x:
            gui_col = _nearest(gui_col_base, gui_col_center, gui_col_wrap_period)
        if wrap_y:
            gui_row = _nearest(gui_row_base, gui_row_center, gui_row_wrap_period)

        if gui_col_lo <= gui_col < gui_col_hi and gui_row_lo <= gui_row < gui_row_hi:
            result[(mx, my)] = (
                gui_col - gui_col_viewport_origin,
                gui_row - gui_row_viewport_origin,
            )
    return result


# ---------------------------------------------------------------------------
# Main renderer
# ---------------------------------------------------------------------------


def render_map_centered(
    tiles: list[dict],
    units: list[dict],
    map_width: int,
    map_height: int,
    topology_id: int,
    gui_col_center: int,
    gui_row_center: int,
    viewport_cols: int,
    viewport_rows: int,
    wrap_x: bool = True,
    wrap_y: bool = False,
    label_coords: bool = False,
) -> str:
    """Render a viewport centred on GUI position (gui_col_center, gui_row_center).

    Pass GUI coords directly so callers can average in GUI space and avoid
    the iso-hex MAP-coord averaging artifact.
    Works for all 4 Freeciv topology modes (id 0-3).
    """

    own_units_map: dict[tuple[int, int], list[str]] = {}
    for u in units:
        own_units_map.setdefault((u["x"], u["y"]), []).append(u["type"])

    use_hex = topology_id in (2, 3)
    canvas = MapCanvas(viewport_cols, viewport_rows)
    tiles_by_pos = {(t["x"], t["y"]): t for t in tiles}

    def _draw_tile(t: dict, canvas_col: int, canvas_row: int) -> None:
        if label_coords:
            known = t.get("known", 0)
            bg = terrain_bg(t.get("terrain") or "") if known == 2 else BG_UNKNOWN
            tl_ch, tl_fg = str(t["x"]), FG_CONTENT
            tr_ch, tr_fg = str(t["y"]), FG_CONTENT
            bl_ch, bl_fg = " ", FG_CONTENT
            br_ch, br_fg = " ", FG_CONTENT
            border = FG_BORDER_VISIBLE
        else:
            bg, tl_ch, tl_fg, tr_ch, tr_fg, bl_ch, bl_fg, br_ch, br_fg, border = (
                _cell_colors(t, own_units_map)
            )
        if use_hex:
            _draw_hex_cell(
                canvas,
                canvas_col,
                canvas_row,
                bg,
                tl_ch,
                tl_fg,
                tr_ch,
                tr_fg,
                bl_ch,
                bl_fg,
                br_ch,
                br_fg,
                border,
            )
        else:
            _draw_square_cell(
                canvas,
                canvas_col,
                canvas_row,
                bg,
                tl_ch,
                tl_fg,
                tr_ch,
                tr_fg,
                bl_ch,
                bl_fg,
                br_ch,
                br_fg,
                border,
            )

    layout = _tile_layout(
        tiles,
        map_width,
        map_height,
        topology_id,
        gui_col_center,
        gui_row_center,
        viewport_cols,
        viewport_rows,
        wrap_x,
        wrap_y,
    )
    for (mx, my), (canvas_col, canvas_row) in layout.items():
        t = tiles_by_pos[(mx, my)]
        _draw_tile(t, canvas_col, canvas_row)

    return canvas.render()


def render_isohex_centered(
    tiles: list[dict],
    units: list[dict],
    map_width: int,
    map_height: int,
    gui_col_center: int,
    gui_row_center: int,
    viewport_cols: int,
    viewport_rows: int,
    topology_id: int = 3,
    wrap_x: bool = True,
    wrap_y: bool = False,
) -> str:
    """Wrapper around render_map_centered. Center in GUI coords (gui_col, gui_row)."""
    return render_map_centered(
        tiles,
        units,
        map_width,
        map_height,
        topology_id,
        gui_col_center,
        gui_row_center,
        viewport_cols,
        viewport_rows,
        wrap_x=wrap_x,
        wrap_y=wrap_y,
    )


# ---------------------------------------------------------------------------
# ANSI + display panel helpers
# ---------------------------------------------------------------------------

_ANSI_RE = re.compile(r"\033\[[^m]*m")


def visible_len(s: str) -> int:
    return len(_ANSI_RE.sub("", s))


def rpad(s: str, width: int) -> str:
    return s + " " * max(0, width - visible_len(s))


def units_panel_lines(units: list[dict]) -> list[str]:
    if not units:
        return ["(no units)"]
    lines = [f"=== Units ({len(units)}) ==="]
    for u in units:
        lines.append(
            f"[{u['id']:5d}] {u['type']:16s}"
            f" ({u['x']:3d},{u['y']:3d})"
            f" HP{u['hp']:3d}/{u['hp_max']:<3d}"
            f" mv{u['moves_left']}/{u['moves_max']}"
        )
    return lines


def map_legend() -> str:
    R = MAP_RESET
    lines: list[str] = []

    lines.append("=== Map Legend ===")

    terrain_entries = []
    for name, color in sorted(_TERRAIN_BG.items()):
        if name == "coast":
            continue
        swatch = f"{_bg(color)}{_fg(FG_CONTENT)}   {R}"
        terrain_entries.append(f"{swatch} {name.capitalize()}")
    unknown = f"{_bg(BG_UNKNOWN)}{_fg(FG_CONTENT)}   {R} Unexplored/fogged"
    terrain_entries.append(unknown)

    lines.append("Terrain:")
    terrain_width = max((visible_len(entry) for entry in terrain_entries), default=0)
    for start in range(0, len(terrain_entries), 3):
        chunk = terrain_entries[start:start + 3]
        lines.append("  " + "  ".join(rpad(entry, terrain_width) for entry in chunk))

    lines.append("Slots (TL=city, TR/BL/BR=units):")
    lines.append(
        "  "
        f"{_fg(FG_CITY)}R{R} city"
        f"  {_fg(FG_OWN_UNIT)}S{R} own unit"
        f"  {_fg(FG_OWN_UNIT)}3{R} own overflow"
    )
    lines.append(
        "  "
        f"{_fg(FG_ENEMY)}u{R} enemy unit"
        f"  {_fg(FG_ENEMY)}4{R} enemy count"
    )

    return "\n".join(lines)
