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


def _map_bg(code: int) -> str:
    return f"\033[48;5;{code}m"


def _map_fg(code: int) -> str:
    return f"\033[38;5;{code}m"


MAP_RESET = "\033[0m"

_TERRAIN_BG: dict[str, int] = {
    "ocean":      21,
    "lake":       27,
    "coast":      33,
    "grassland":  34,
    "plains":    100,
    "desert":    220,
    "mountains": 240,
    "hills":     130,
    "forest":     22,
    "jungle":     28,
    "tundra":    153,
    "arctic":    231,
    "swamp":      23,
}
BG_UNKNOWN = 232   # near-black — tile never seen
BG_FOGGED  = 238   # dark grey  — seen before but currently fogged
BG_DEFAULT = 241   # fallback for visible tiles with unknown terrain name
FG_CONTENT = 15    # bright white
FG_BORDER  = 237   # dark grey border characters


def terrain_bg(terrain: str) -> int:
    return _TERRAIN_BG.get(terrain.lower(), BG_DEFAULT)


class MapCanvas:
    """Fixed-size character + colour canvas for map rendering."""

    def __init__(self, cols: int, rows: int) -> None:
        self.cols = cols
        self.rows = rows
        self._ch: list[list[str]] = [[" "] * cols for _ in range(rows)]
        self._fg: list[list[int]] = [[-1] * cols for _ in range(rows)]
        self._bg: list[list[int]] = [[-1] * cols for _ in range(rows)]

    def put(self, col: int, row: int, ch: str,
            fg: int = FG_CONTENT, bg: int = -1) -> None:
        if 0 <= col < self.cols and 0 <= row < self.rows:
            self._ch[row][col] = ch
            self._fg[row][col] = fg
            self._bg[row][col] = bg

    def render(self) -> str:
        lines: list[str] = []
        for row in range(self.rows):
            parts: list[str] = []
            cur_fg = cur_bg = -1
            for col in range(self.cols):
                ch = self._ch[row][col]
                fg = self._fg[row][col]
                bg = self._bg[row][col]
                esc = ""
                if fg != cur_fg:
                    esc += _map_fg(fg) if fg >= 0 else "\033[39m"
                    cur_fg = fg
                if bg != cur_bg:
                    esc += _map_bg(bg) if bg >= 0 else "\033[49m"
                    cur_bg = bg
                parts.append(esc + ch)
            lines.append("".join(parts) + MAP_RESET)
        return "\n".join(lines)


def map_pos_to_native(mx: int, my: int, map_width: int) -> tuple[int, int]:
    """Convert Freeciv iso MAP coordinates to NATIVE (display) coordinates."""
    nat_y = mx + my - map_width
    nat_x = (2 * mx - nat_y - (nat_y & 1)) // 2
    return nat_x, nat_y


def _tile_marker(tile: dict, own_units_map: dict[tuple[int, int], list[str]]) -> tuple[str, str]:
    """Return (terrain_initial, unit_marker) for a visible tile."""
    terrain = tile.get("terrain") or ""
    x_ch = terrain[0].upper() if terrain else "?"
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


def _draw_cell(canvas: MapCanvas, cc: int, cr: int, bg: int,
               x_ch: str, y_ch: str) -> None:
    canvas.put(cc + 0, cr, "/",  fg=FG_BORDER,  bg=bg)
    canvas.put(cc + 1, cr, x_ch, fg=FG_CONTENT, bg=bg)
    canvas.put(cc + 2, cr, " ",  fg=FG_CONTENT, bg=bg)
    canvas.put(cc + 3, cr, "\\", fg=FG_BORDER,  bg=bg)
    u_ch = y_ch if y_ch != " " else "_"
    canvas.put(cc + 0, cr + 1, "\\", fg=FG_BORDER,  bg=bg)
    canvas.put(cc + 1, cr + 1, "_",  fg=FG_BORDER,  bg=bg)
    canvas.put(cc + 2, cr + 1, u_ch, fg=FG_CONTENT if y_ch != " " else FG_BORDER, bg=bg)
    canvas.put(cc + 3, cr + 1, "/",  fg=FG_BORDER,  bg=bg)


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
        known = tile["known"]
        if known == 0:
            _draw_cell(canvas, cc, cr, BG_UNKNOWN, " ", " ")
        else:
            bg = terrain_bg(tile.get("terrain") or "") if known == 2 else BG_FOGGED
            x_ch, y_ch = _tile_marker(tile, own_units_map)
            _draw_cell(canvas, cc, cr, bg, x_ch, y_ch)

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
        if tile is None:
            _draw_cell(canvas, cc, cr, BG_UNKNOWN, " ", " ")
        else:
            known = tile["known"]
            if known == 0:
                _draw_cell(canvas, cc, cr, BG_UNKNOWN, " ", " ")
            else:
                bg = terrain_bg(tile.get("terrain") or "") if known == 2 else BG_FOGGED
                x_ch, y_ch = _tile_marker(tile, own_units_map)
                _draw_cell(canvas, cc, cr, bg, x_ch, y_ch)

    return canvas.render()


# ── ANSI + DISPLAY PANEL HELPERS ──────────────────────────────────────────────

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
    for name, code in sorted(_TERRAIN_BG.items()):
        initial = name[0].upper()
        swatch = f"{_map_bg(code)}{_map_fg(FG_CONTENT)} {initial} {R}"
        lines.append(f"  {swatch}  {name.capitalize()}")
    fogged  = f"{_map_bg(BG_FOGGED)}{_map_fg(FG_CONTENT)} ? {R}"
    unknown = f"{_map_bg(BG_UNKNOWN)}{_map_fg(FG_CONTENT)}   {R}"
    lines.append(f"  {fogged}  Fogged (seen, not visible now)")
    lines.append(f"  {unknown}  Unexplored\n")

    lines.append("Unit/city markers (bottom-right of cell):")
    lines.append("  C        City present")
    lines.append("  A-Z      Your unit type initial (e.g. S=Settlers, W=Workers)")
    lines.append("  u        Enemy/neutral unit (type unknown)")
    lines.append("  2-9      Multiple units on tile")
    lines.append("  +        10 or more units on tile")

    return "\n".join(lines)
