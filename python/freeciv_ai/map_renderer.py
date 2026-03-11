"""Freeciv map renderer — supports all 4 topology modes.

Topology IDs (bitmask: TF_ISO=1, TF_HEX=2):
  0  flat square  — simple rectangular grid
  1  iso square   — isometric diamond view
  2  flat hex     — row-staggered hex grid (N/NE/E/W/SW/S valid)
  3  iso-hex      — isometric hex, beehive layout (N/NW/W/E/S/SE valid)

GUI coordinate mapping (MAP → char canvas):

  id=0  gc = mx * 4              gr = my * 2        step-4 square grid
  id=1  gc = (mx-my) * 4        gr = (mx+my) * 2   iso diamond, step-4
  id=2  gc = mx*4 + (my%2)*2    gr = my * 2        row-stagger hex, step-4
  id=3  gc = (mx-my) * 3        gr = mx + my       iso beehive, step-3 (rows shared)

For id=3 adjacent tiles differ by Δgc=±3, Δgr=±1 (E/S/N/W dirs) so their
/\\ and \\/ edge characters land on the same canvas column — forming the
beehive.  The NW/SE dirs differ by Δgc=0, Δgr=±2 (directly above/below,
sharing the __ cap).

Center coords passed to render_map_centered() are always MAP coords (mx, my).
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

def _map_bg(c: Color) -> str: return _bg(c)
def _map_fg(c: Color) -> str: return _fg(c)

# ---------------------------------------------------------------------------
# Terrain palette
# ---------------------------------------------------------------------------

_TERRAIN_BG: dict[str, Color] = {
    "ocean":       (  0,  80, 180),
    "deep ocean":  (  0,  50, 130),
    "lake":        ( 30, 120, 200),
    "coast":       ( 70, 160, 220),
    "grassland":   ( 55, 160,  45),
    "plains":      (185, 175,  70),
    "desert":      (215, 195,  75),
    "mountains":   (120, 110, 100),
    "hills":       (145, 100,  55),
    "forest":      ( 25, 105,  35),
    "jungle":      ( 15, 135,  50),
    "tundra":      (140, 165, 195),
    "arctic":      (210, 230, 255),
    "glacier":     (210, 230, 255),
    "swamp":       ( 50,  95,  65),
    "inaccessible":(  5,   5,   5),
}

BG_UNKNOWN: Color = ( 12,  12,  12)
BG_FOGGED:  Color = ( 32,  30,  28)
BG_DEFAULT: Color = ( 90,  90,  90)
FG_CONTENT: Color = (255, 255, 255)
FG_BORDER:  Color = ( 50,  45,  35)
FG_BORDER_VISIBLE = FG_BORDER

# Foreground colors for notable tile objects
FG_CITY:     Color = (255, 220,  50)   # gold
FG_OWN_UNIT: Color = (120, 230, 255)   # light cyan
FG_ENEMY:    Color = (255, 110,  80)   # orange-red

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
        self._ch: list[list[str]]   = [[" "] * cols for _ in range(rows)]
        self._fg: list[list[Color]] = [[_NO_COLOR]  * cols for _ in range(rows)]
        self._bg: list[list[Color]] = [[_NO_COLOR]  * cols for _ in range(rows)]

    def put(self, col: int, row: int, ch: str,
            fg: Color = FG_CONTENT, bg: Color = _NO_COLOR) -> None:
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
    if topo == 3:   return (mx - my) * 3, mx + my          # iso-hex beehive
    if topo == 1:   return (mx - my) * 4, (mx + my) * 2    # iso-square diamond
    if topo == 2:   return mx * 4 + (my % 2) * 2, my * 2   # flat-hex row-stagger
    return mx * 4, my * 2                                   # flat-square

def _gc_x_period(topo: int, map_width: int) -> int:
    """gc shift when mx increases by map_width (x-wrap period)."""
    if topo in (1, 3): return (4 if topo == 1 else 3) * map_width
    return 4 * map_width

def _gr_y_period(topo: int, map_height: int) -> int:
    """gr shift when my increases by map_height (y-wrap period)."""
    if topo == 3: return map_height          # gr = mx+my, only my contributes
    return 2 * map_height                    # gr = my*2 (or (mx+my)*2)

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
    canvas: MapCanvas, cc: int, cr: int, bg: Color,
    tl_ch: str, tl_fg: Color,
    tr_ch: str, tr_fg: Color,
    bl_ch: str, bl_fg: Color,
    br_ch: str, br_fg: Color,
    border: Color = FG_BORDER,
) -> None:
    """Draw a hex cell — 4 chars wide, 2 rows tall.

      / TL TR \\
      \\ BL BR /
    """
    canvas.put(cc,     cr,   "/",   fg=border, bg=bg)
    canvas.put(cc + 1, cr,   tl_ch, fg=tl_fg,  bg=bg)
    canvas.put(cc + 2, cr,   tr_ch, fg=tr_fg,  bg=bg)
    canvas.put(cc + 3, cr,   "\\",  fg=border, bg=bg)
    canvas.put(cc,     cr+1, "\\",  fg=border, bg=bg)
    canvas.put(cc + 1, cr+1, bl_ch, fg=bl_fg,  bg=bg)
    canvas.put(cc + 2, cr+1, br_ch, fg=br_fg,  bg=bg)
    canvas.put(cc + 3, cr+1, "/",   fg=border, bg=bg)


def _draw_square_cell(
    canvas: MapCanvas, cc: int, cr: int, bg: Color,
    tl_ch: str, tl_fg: Color,
    tr_ch: str, tr_fg: Color,
    bl_ch: str, bl_fg: Color,
    br_ch: str, br_fg: Color,
    border: Color = FG_BORDER,
) -> None:
    """Draw a square cell — 4 chars wide, 2 rows tall.

      TL TR . .
      BL BR . .
    """
    canvas.put(cc,     cr,   tl_ch, fg=tl_fg,  bg=bg)
    canvas.put(cc + 1, cr,   tr_ch, fg=tr_fg,  bg=bg)
    canvas.put(cc + 2, cr,   " ",   fg=border, bg=bg)
    canvas.put(cc + 3, cr,   " ",   fg=border, bg=bg)
    canvas.put(cc,     cr+1, bl_ch, fg=bl_fg,  bg=bg)
    canvas.put(cc + 1, cr+1, br_ch, fg=br_fg,  bg=bg)
    canvas.put(cc + 2, cr+1, " ",   fg=border, bg=bg)
    canvas.put(cc + 3, cr+1, " ",   fg=border, bg=bg)


# ---------------------------------------------------------------------------
# Main renderer
# ---------------------------------------------------------------------------

def render_map_centered(
    tiles: list[dict],
    units: list[dict],
    map_width: int,
    map_height: int,
    topology_id: int,
    gc_ctr: int,
    gr_ctr: int,
    viewport_cols: int,
    viewport_rows: int,
    wrap_x: bool = True,
    wrap_y: bool = False,
) -> str:
    """Render a viewport centred on GUI position (gc_ctr, gr_ctr).

    Pass GUI coords directly so callers can average in GUI space and avoid
    the iso-hex MAP-coord averaging artifact.
    Works for all 4 Freeciv topology modes (id 0-3).
    """

    own_units_map: dict[tuple[int, int], list[str]] = {}
    for u in units:
        own_units_map.setdefault((u["x"], u["y"]), []).append(u["type"])

    use_hex = topology_id in (2, 3)
    gc_period = _gc_x_period(topology_id, map_width)
    gr_period = _gr_y_period(topology_id, map_height)

    # Canvas always fills the full terminal so the map is centered on screen.
    canvas = MapCanvas(viewport_cols, viewport_rows)

    # Place the center tile in the middle of the canvas.
    gc_min = gc_ctr + 2 - viewport_cols // 2
    gr_min = gr_ctr + 1 - viewport_rows // 2
    gc_lo, gc_hi = gc_min - 3, gc_min + viewport_cols
    gr_lo, gr_hi = gr_min - 1, gr_min + viewport_rows

    def _draw_tile(t: dict, cc: int, cr: int) -> None:
        bg, tl_ch, tl_fg, tr_ch, tr_fg, bl_ch, bl_fg, br_ch, br_fg, border = _cell_colors(t, own_units_map)
        if use_hex:
            _draw_hex_cell(canvas, cc, cr, bg, tl_ch, tl_fg, tr_ch, tr_fg, bl_ch, bl_fg, br_ch, br_fg, border)
        else:
            _draw_square_cell(canvas, cc, cr, bg, tl_ch, tl_fg, tr_ch, tr_fg, bl_ch, bl_fg, br_ch, br_fg, border)

    def _nearest(base: int, ctr: int, period: int) -> int:
        """Shift base by a multiple of period to land closest to ctr."""
        d = (base - ctr) % period
        if d > period // 2:
            d -= period
        return ctr + d

    for t in tiles:
        mx, my = t["x"], t["y"]
        gc_base, gr_base = _gui_pos(mx, my, topology_id)

        gc = _nearest(gc_base, gc_ctr, gc_period) if wrap_x else gc_base
        gr = _nearest(gr_base, gr_ctr, gr_period) if wrap_y else gr_base

        if gc_lo <= gc < gc_hi and gr_lo <= gr < gr_hi:
            _draw_tile(t, gc - gc_min, gr - gr_min)

    return canvas.render()


# ---------------------------------------------------------------------------
# Legacy range-based renderer (kept for 'map x1:x2 y1:y2' command)
# ---------------------------------------------------------------------------

def render_isohex(
    tiles: list[dict],
    units: list[dict],
    map_width: int = 0,   # noqa: ARG001 (unused; kept for call-site compatibility)
    map_height: int = 0,  # noqa: ARG001
    x_range: tuple[int, int] | None = None,
    y_range: tuple[int, int] | None = None,
    topology_id: int = 3,
) -> str:
    """Render a MAP-coord filtered slice. x_range/y_range filter on mx/my."""
    x_min = x_range[0] if x_range else None
    x_max = x_range[1] if x_range else None
    y_min = y_range[0] if y_range else None
    y_max = y_range[1] if y_range else None

    filtered: list[dict] = []
    for t in tiles:
        mx, my = t["x"], t["y"]
        if x_min is not None and not (x_min <= mx < x_max):
            continue
        if y_min is not None and not (y_min <= my < y_max):
            continue
        filtered.append(t)

    if not filtered:
        return "(no tiles in range)"

    all_gc = [_gui_pos(t["x"], t["y"], topology_id)[0] for t in filtered]
    all_gr = [_gui_pos(t["x"], t["y"], topology_id)[1] for t in filtered]
    gc_min, gc_max = min(all_gc), max(all_gc)
    gr_min, gr_max = min(all_gr), max(all_gr)

    canvas_cols = (gc_max - gc_min) + 4 + 4
    canvas_rows = (gr_max - gr_min) + 2 + 2
    canvas = MapCanvas(canvas_cols, canvas_rows)

    own_units_map: dict[tuple[int, int], list[str]] = {}
    for u in units:
        own_units_map.setdefault((u["x"], u["y"]), []).append(u["type"])

    use_hex = topology_id in (2, 3)
    for t in filtered:
        gc, gr = _gui_pos(t["x"], t["y"], topology_id)
        cc = gc - gc_min
        cr = gr - gr_min
        bg, tl_ch, tl_fg, tr_ch, tr_fg, bl_ch, bl_fg, br_ch, br_fg, border = _cell_colors(t, own_units_map)
        if use_hex:
            _draw_hex_cell(canvas, cc, cr, bg, tl_ch, tl_fg, tr_ch, tr_fg, bl_ch, bl_fg, br_ch, br_fg, border)
        else:
            _draw_square_cell(canvas, cc, cr, bg, tl_ch, tl_fg, tr_ch, tr_fg, bl_ch, bl_fg, br_ch, br_fg, border)

    return canvas.render()


def render_isohex_centered(
    tiles: list[dict],
    units: list[dict],
    map_width: int,
    map_height: int,
    gc_ctr: int,
    gr_ctr: int,
    viewport_cols: int,
    viewport_rows: int,
    topology_id: int = 3,
    wrap_x: bool = True,
    wrap_y: bool = False,
) -> str:
    """Wrapper around render_map_centered. Center in GUI coords (gc, gr)."""
    return render_map_centered(
        tiles, units, map_width, map_height, topology_id,
        gc_ctr, gr_ctr, viewport_cols, viewport_rows, wrap_x=wrap_x, wrap_y=wrap_y,
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


def parse_map_range(token: str) -> tuple[int, int]:
    parts = token.split(":")
    if len(parts) != 2:
        raise ValueError(f"expected 'a:b', got {token!r}")
    return int(parts[0]), int(parts[1])


def map_legend() -> str:
    R = MAP_RESET
    lines: list[str] = []

    lines.append("=== Map Legend ===")

    lines.append("Terrain:")
    for name, color in sorted(_TERRAIN_BG.items()):
        if name in ("coast",):
            continue
        swatch = f"{_bg(color)}{_fg(FG_CONTENT)}   {R}"
        lines.append(f"  {swatch} {name.capitalize()}")
    unknown = f"{_bg(BG_UNKNOWN)}{_fg(FG_CONTENT)}   {R}"
    lines.append(f"  {unknown} Unexplored/fogged")

    lines.append("Slots (TL=city, TR/BL/BR=units):")
    lines.append(f"  {_fg(FG_CITY)}R{R} city initial (gold)")
    lines.append(f"  {_fg(FG_OWN_UNIT)}S{R} own unit initial (cyan)  {_fg(FG_OWN_UNIT)}3{R} count if overflow")
    lines.append(f"  {_fg(FG_ENEMY)}u{R} enemy unit  {_fg(FG_ENEMY)}4{R} enemy count")

    return "\n".join(lines)
