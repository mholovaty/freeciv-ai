"""ISO-hex map renderer for the Freeciv AI client.

Coordinate maths (topology TF_ISO|TF_HEX, id=3)
-------------------------------------------------
get_map() returns MAP coordinates (mx, my).  For Freeciv iso maps the
NATIVE (screen) coordinates are obtained via MAP_TO_NATIVE_POS:

  nat_y = mx + my - MAP_NATIVE_WIDTH   (MAP_NATIVE_WIDTH == map_width)
  nat_x = (2*mx - nat_y - (nat_y & 1)) / 2

nat_x ∈ [0, map_width-1], nat_y ∈ [0, map_height-1].

The native grid is a flat staggered hex layout:
  - Even nat_y rows start at char_col 0
  - Odd  nat_y rows are shifted right by 2 chars (half cell)

Cell shape (4 wide, 2 rows):

  char_col+0..3  ->  "/XY\\"    (char_row)
  char_col+0..3  ->  "\\__/"    (char_row + 1)

char_col = nat_x * 4 + (nat_y % 2) * 2
char_row = nat_y * 2
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

# Keep old names as aliases so repl.py import works unchanged
def _map_bg(c: Color) -> str: return _bg(c)
def _map_fg(c: Color) -> str: return _fg(c)

# ---------------------------------------------------------------------------
# Terrain palette (visible, full brightness)
# ---------------------------------------------------------------------------

_TERRAIN_BG: dict[str, Color] = {
    "ocean":       (  0,  80, 180),
    "deep ocean":  (  0,  50, 130),
    "lake":        ( 30, 120, 200),
    "coast":       ( 70, 160, 220),   # kept as alias
    "grassland":   ( 55, 160,  45),
    "plains":      (185, 175,  70),
    "desert":      (215, 195,  75),
    "mountains":   (120, 110, 100),
    "hills":       (145, 100,  55),
    "forest":      ( 25, 105,  35),
    "jungle":      ( 15, 135,  50),
    "tundra":      (140, 165, 195),
    "arctic":      (210, 230, 255),
    "glacier":     (210, 230, 255),   # same as arctic
    "swamp":       ( 50,  95,  65),
    "inaccessible":(  5,   5,   5),
}

# Sentinel / fallbacks
BG_UNKNOWN: Color = ( 12,  12,  12)   # near-black — tile never seen
BG_FOGGED:  Color = ( 32,  30,  28)   # slightly lighter dark — seen but not currently visible
BG_DEFAULT: Color = ( 90,  90,  90)   # fallback for unknown terrain name
FG_CONTENT: Color = (255, 255, 255)   # bright white text
FG_BORDER: Color = ( 50,  45,  35)   # very dark — subtle on terrain
FG_BORDER_VISIBLE = FG_BORDER  # alias kept for call sites



_TERRAIN_INITIAL: dict[str, str] = {
    "deep ocean": "~",
    "inaccessible": "X",
}

def terrain_bg(terrain: str) -> Color:
    return _TERRAIN_BG.get(terrain.lower(), BG_DEFAULT)

def _terrain_initial(terrain: str) -> str:
    return _TERRAIN_INITIAL.get(terrain.lower(), terrain[0].upper() if terrain else "?")


# ---------------------------------------------------------------------------
# Canvas
# ---------------------------------------------------------------------------

_NO_COLOR: Color = (-1, -1, -1)  # sentinel: inherit / no explicit color

class MapCanvas:
    """Fixed-size character + colour canvas for map rendering."""

    def __init__(self, cols: int, rows: int) -> None:
        self.cols = cols
        self.rows = rows
        self._ch: list[list[str]]   = [[" "] * cols for _ in range(rows)]
        self._fg: list[list[Color]] = [[ _NO_COLOR] * cols for _ in range(rows)]
        self._bg: list[list[Color]] = [[ _NO_COLOR] * cols for _ in range(rows)]

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
# Coordinate conversion
# ---------------------------------------------------------------------------

def map_pos_to_native(mx: int, my: int, map_width: int) -> tuple[int, int]:
    """Convert Freeciv iso MAP coordinates to NATIVE (display) coordinates."""
    nat_y = mx + my - map_width
    nat_x = (2 * mx - nat_y - (nat_y & 1)) // 2
    return nat_x, nat_y


# ---------------------------------------------------------------------------
# Cell drawing helpers
# ---------------------------------------------------------------------------

def _tile_marker(tile: dict, own_units_map: dict[tuple[int, int], list[str]]) -> tuple[str, str]:
    """Return (terrain_initial, unit_marker) for a visible tile."""
    terrain = tile.get("terrain") or ""
    x_ch = _terrain_initial(terrain)
    city_id = tile.get("city_id", -1)
    n_units = tile.get("n_units", 0)
    map_key = (tile["x"], tile["y"])
    if city_id >= 0:
        y_ch = "C"
    elif map_key in own_units_map:
        own = own_units_map[map_key]
        if len(own) == 1:
            y_ch = own[0][0].upper() if own[0] else "U"
        else:
            y_ch = str(len(own)) if len(own) <= 9 else "+"
    elif n_units >= 2:
        y_ch = str(n_units) if n_units <= 9 else "+"
    elif n_units == 1:
        y_ch = "u"
    else:
        y_ch = " "
    return x_ch, y_ch


def _draw_cell(canvas: MapCanvas, cc: int, cr: int, bg: Color,
               x_ch: str, y_ch: str, border: Color = FG_BORDER) -> None:
    canvas.put(cc + 0, cr, "/",  fg=border,     bg=bg)
    canvas.put(cc + 1, cr, x_ch, fg=FG_CONTENT, bg=bg)
    canvas.put(cc + 2, cr, " ",  fg=FG_CONTENT, bg=bg)
    canvas.put(cc + 3, cr, "\\", fg=border,     bg=bg)
    u_ch = y_ch if y_ch != " " else "_"
    canvas.put(cc + 0, cr + 1, "\\", fg=border,     bg=bg)
    canvas.put(cc + 1, cr + 1, "_",  fg=border,     bg=bg)
    canvas.put(cc + 2, cr + 1, u_ch, fg=FG_CONTENT if y_ch != " " else border, bg=bg)
    canvas.put(cc + 3, cr + 1, "/",  fg=border,     bg=bg)


def _cell_colors(tile: dict | None, own_units_map: dict) -> tuple[Color, str, str, Color]:
    """Return (bg_color, terrain_ch, unit_ch, border_color) for a tile."""
    if tile is None:
        return BG_UNKNOWN, " ", " ", FG_BORDER
    known = tile["known"]
    if known == 0:
        return BG_UNKNOWN, " ", " ", FG_BORDER
    bg = terrain_bg(tile.get("terrain") or "")
    if known == 2:
        x_ch, y_ch = _tile_marker(tile, own_units_map)
        return bg, x_ch, y_ch, FG_BORDER_VISIBLE
    else:
        # fogged: terrain color but no text
        return bg, " ", " ", FG_BORDER


# ---------------------------------------------------------------------------
# Public renderers
# ---------------------------------------------------------------------------

def render_isohex(
    tiles: list[dict],
    units: list[dict],
    map_width: int,
    map_height: int,
    x_range: tuple[int, int] | None = None,
    y_range: tuple[int, int] | None = None,
) -> str:
    """Render a filtered iso-hex map slice as a coloured ANSI string."""
    x_min = x_range[0] if x_range else None
    x_max = x_range[1] if x_range else None
    y_min = y_range[0] if y_range else None
    y_max = y_range[1] if y_range else None

    tile_map: dict[tuple[int, int], dict] = {}
    for t in tiles:
        mx, my = t["x"], t["y"]
        nat_x, nat_y = map_pos_to_native(mx, my, map_width)
        if x_min is not None and not (x_min <= nat_x < x_max):
            continue
        if y_min is not None and not (y_min <= nat_y < y_max):
            continue
        tile_map[(nat_x, nat_y)] = t

    if not tile_map:
        return "(no tiles in range)"

    own_units_map: dict[tuple[int, int], list[str]] = {}
    for u in units:
        key = (u["x"], u["y"])
        own_units_map.setdefault(key, []).append(u["type"])

    all_nat_x = [k[0] for k in tile_map]
    all_nat_y = [k[1] for k in tile_map]
    nx_min, nx_max = min(all_nat_x), max(all_nat_x)
    ny_min, ny_max = min(all_nat_y), max(all_nat_y)

    canvas_cols = (nx_max - nx_min) * 4 + (1 if (ny_max % 2) else 0) * 2 + 4 + 2
    canvas_rows = (ny_max - ny_min) * 2 + 2
    canvas = MapCanvas(canvas_cols, canvas_rows)

    for (nat_x, nat_y), tile in tile_map.items():
        stagger = (nat_y % 2) * 2
        cc = (nat_x - nx_min) * 4 + stagger
        cr = (nat_y - ny_min) * 2
        bg, x_ch, y_ch, border = _cell_colors(tile, own_units_map)
        _draw_cell(canvas, cc, cr, bg, x_ch, y_ch, border)

    return canvas.render()


def render_isohex_centered(
    tiles: list[dict],
    units: list[dict],
    map_width: int,
    map_height: int,
    cx: int,
    cy: int,
    viewport_cols: int,
    viewport_rows: int,
) -> str:
    """Render a wrap-aware iso-hex viewport centred on native (cx, cy)."""
    ncols = min(max(1, (viewport_cols - 2) // 4), map_width)
    nrows = min(max(1, viewport_rows // 2), map_height)
    x0 = cx - ncols // 2
    y0 = cy - nrows // 2

    vp_to_nat: dict[tuple[int, int], tuple[int, int]] = {}
    nat_to_vp: dict[tuple[int, int], tuple[int, int]] = {}
    for vy in range(nrows):
        for vx in range(ncols):
            nx = (x0 + vx) % map_width
            ny = (y0 + vy) % map_height
            vp_to_nat[(vx, vy)] = (nx, ny)
            nat_to_vp[(nx, ny)] = (vx, vy)

    tile_map: dict[tuple[int, int], dict] = {}
    for t in tiles:
        mx, my = t["x"], t["y"]
        nx, ny = map_pos_to_native(mx, my, map_width)
        if (nx, ny) in nat_to_vp:
            tile_map[(nx, ny)] = t

    own_units_map: dict[tuple[int, int], list[str]] = {}
    for u in units:
        key = (u["x"], u["y"])
        own_units_map.setdefault(key, []).append(u["type"])

    canvas = MapCanvas(ncols * 4 + 2, nrows * 2)

    for (vx, vy), (nx, ny) in vp_to_nat.items():
        tile = tile_map.get((nx, ny))
        stagger = (ny % 2) * 2
        cc = vx * 4 + stagger
        cr = vy * 2
        bg, x_ch, y_ch, border = _cell_colors(tile, own_units_map)
        _draw_cell(canvas, cc, cr, bg, x_ch, y_ch, border)

    return canvas.render()


# ---------------------------------------------------------------------------
# ANSI + display panel helpers
# ---------------------------------------------------------------------------

_ANSI_RE = re.compile(r"\033\[[^m]*m")


def visible_len(s: str) -> int:
    """Visible (non-ANSI) character count of a string."""
    return len(_ANSI_RE.sub("", s))


def rpad(s: str, width: int) -> str:
    """Right-pad s to `width` visible chars."""
    return s + " " * max(0, width - visible_len(s))


def units_panel_lines(units: list[dict]) -> list[str]:
    """Format own units as a list of strings for the display panel."""
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
    """Parse 'a:b' into (a, b). Raises ValueError on bad input."""
    parts = token.split(":")
    if len(parts) != 2:
        raise ValueError(f"expected 'a:b', got {token!r}")
    return int(parts[0]), int(parts[1])


def map_legend() -> str:
    """Return a coloured legend explaining the map symbols."""
    R = MAP_RESET
    lines: list[str] = []

    lines.append("=== Map Legend ===\n")

    lines.append("Cell layout:")
    lines.append("  /T \\    T = terrain initial")
    lines.append("  \\_U/    U = unit/city marker (bottom-right)\n")

    lines.append("Terrain colours & initials:")
    for name, color in sorted(_TERRAIN_BG.items()):
        if name in ("coast",):  # alias, skip duplicate
            continue
        initial = _terrain_initial(name)
        swatch = f"{_bg(color)}{_fg(FG_CONTENT)} {initial} {R}"
        lines.append(f"  {swatch}  {name.capitalize()}")

    unknown = f"{_bg(BG_UNKNOWN)}{_fg(FG_CONTENT)}   {R}"
    fogged_ex = f"{_bg(_TERRAIN_BG['grassland'])}{_fg(FG_CONTENT)}   {R}"
    lines.append(f"  {unknown}  Unexplored (never seen)")
    lines.append(f"  {fogged_ex}  Fogged (seen, not visible — terrain colour shown, no letter)\n")

    lines.append("Unit/city markers (bottom-right of cell):")
    lines.append("  C        City present")
    lines.append("  A-Z      Your unit type initial (e.g. S=Settlers, W=Workers)")
    lines.append("  u        Enemy/neutral unit (type unknown)")
    lines.append("  2-9      Multiple units on tile")
    lines.append("  +        10 or more units on tile")

    return "\n".join(lines)
