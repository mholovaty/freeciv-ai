"""Visual sanity check for map_renderer topologies using server-style tiles."""

import argparse

from freeciv_ai.map_renderer import _gui_pos, map_pos_to_native, render_map_centered

TOPO_NAMES = {0: "flat-sq", 1: "iso-sq", 2: "flat-hex", 3: "iso-hex"}
TERRAINS = [
    "grassland",
    "plains",
    "desert",
    "forest",
    "ocean",
    "hills",
    "mountains",
    "tundra",
    "jungle",
]


def _native_to_map_pos(nx: int, ny: int, map_width: int, topo: int) -> tuple[int, int]:
    if topo in (1, 3):
        mx = (ny + (ny & 1)) // 2 + nx
        my = ny - mx + map_width
        return mx, my
    return nx, ny


def _server_tiles(topo: int, map_width: int, map_height: int) -> list[dict]:
    if topo in (1, 3) and map_height % 2 != 0:
        raise ValueError(
            f"topo {topo} ({TOPO_NAMES[topo]}) uses native server dimensions; "
            "height must be even on isometric maps"
        )

    tiles: list[dict] = []
    for ny in range(map_height):
        for nx in range(map_width):
            mx, my = _native_to_map_pos(nx, ny, map_width, topo)
            tiles.append(
                {
                    "x": mx,
                    "y": my,
                    "known": 2,
                    "terrain": TERRAINS[(nx + ny * map_width) % len(TERRAINS)],
                    "n_units": 0,
                    "city_id": -1,
                }
            )
    return tiles


def _gui_bounds(topo: int, tiles: list[dict]) -> tuple[int, int, int, int]:
    gui_positions = [_gui_pos(t["x"], t["y"], topo) for t in tiles]
    min_gc = min(gc for gc, _ in gui_positions)
    max_gc = max(gc for gc, _ in gui_positions)
    min_gr = min(gr for _, gr in gui_positions)
    max_gr = max(gr for _, gr in gui_positions)
    return min_gc, max_gc, min_gr, max_gr


def _default_center(topo: int, tiles: list[dict]) -> tuple[int, int]:
    min_gc, max_gc, min_gr, max_gr = _gui_bounds(topo, tiles)
    return (min_gc + max_gc) // 2, (min_gr + max_gr) // 2


def _auto_viewport(topo: int, tiles: list[dict]) -> tuple[int, int]:
    min_gc, max_gc, min_gr, max_gr = _gui_bounds(topo, tiles)
    cell_w, cell_h = (8, 4) if topo in (2, 3) else (7, 3)
    return max_gc - min_gc + cell_w, max_gr - min_gr + cell_h


def _validate_topology_args(
    parser: argparse.ArgumentParser,
    topo: int,
    map_width: int,
    map_height: int,
    center: tuple[int, int] | None,
    vcols: int | None,
    vrows: int | None,
) -> None:
    if map_width <= 0:
        parser.error("--width must be positive")
    if map_height <= 0:
        parser.error("--height must be positive")
    if vcols is not None and vcols <= 0:
        parser.error("--vcols must be positive")
    if vrows is not None and vrows <= 0:
        parser.error("--vrows must be positive")
    if topo in (1, 3) and map_height % 2 != 0:
        parser.error(
            f"topo {topo} ({TOPO_NAMES[topo]}) uses native server dimensions, so --height must be even"
        )
    if center is None:
        return

    cx, cy = center
    tiles = _server_tiles(topo, map_width, map_height)
    if (cx, cy) not in {(t["x"], t["y"]) for t in tiles}:
        parser.error(
            f"--center ({cx},{cy}) is not a real server tile for topo {topo} with native size "
            f"{map_width}x{map_height}"
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Render freeciv map examples")
    parser.add_argument(
        "--topo",
        type=int,
        choices=[0, 1, 2, 3],
        nargs="+",
        default=[2, 3],
        help="Topology IDs to render (default: 2 3)",
    )
    parser.add_argument(
        "--width",
        "-W",
        type=int,
        default=3,
        help="Native map width (default: 3)",
    )
    parser.add_argument(
        "--height",
        "-H",
        type=int,
        default=4,
        help="Native map height (default: 4; isometric topologies require even height)",
    )
    parser.add_argument(
        "--vcols",
        type=int,
        default=None,
        help="Viewport columns (default: derived from rendered tile positions)",
    )
    parser.add_argument(
        "--vrows",
        type=int,
        default=None,
        help="Viewport rows (default: derived from rendered tile positions)",
    )
    parser.add_argument(
        "--wrap-x", action="store_true", default=False, help="Enable x-axis wrapping"
    )
    parser.add_argument(
        "--wrap-y", action="store_true", default=False, help="Enable y-axis wrapping"
    )
    parser.add_argument(
        "--center",
        type=int,
        nargs=2,
        metavar=("X", "Y"),
        default=None,
        help="Center tile MAP coords (default: server-style center tile)",
    )
    parser.add_argument(
        "--no-labels", action="store_true", help="Disable coordinate labels"
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    map_width, map_height = args.width, args.height

    for topo in args.topo:
        _validate_topology_args(
            parser,
            topo,
            map_width,
            map_height,
            tuple(args.center) if args.center else None,
            args.vcols,
            args.vrows,
        )
        tiles = _server_tiles(topo, map_width, map_height)
        auto_cols, auto_rows = _auto_viewport(topo, tiles)
        vcols = args.vcols or auto_cols
        vrows = args.vrows or auto_rows
        if args.center:
            cx, cy = args.center
            gui_col_center, gui_row_center = _gui_pos(cx, cy, topo)
        else:
            gui_col_center, gui_row_center = _default_center(topo, tiles)
            if topo in (1, 3):
                nx = ny = -1
                center_note = f"gui_center=({gui_col_center},{gui_row_center})"
            else:
                center_note = f"gui_center=({gui_col_center},{gui_row_center})"
        if topo in (1, 3):
            if args.center:
                nx, ny = map_pos_to_native(cx, cy, map_width)
                center_note = f"center=({cx},{cy}) native=({nx},{ny})"
        else:
            if args.center:
                center_note = f"center=({cx},{cy})"
        rendered = render_map_centered(
            tiles,
            [],
            map_width,
            map_height,
            topo,
            gui_col_center,
            gui_row_center,
            vcols,
            vrows,
            wrap_x=args.wrap_x,
            wrap_y=args.wrap_y,
            label_coords=not args.no_labels,
        )
        print(
            f"=== topo {topo}: {TOPO_NAMES[topo]} | native={map_width}x{map_height} | "
            f"wrap_x={args.wrap_x} wrap_y={args.wrap_y} | {center_note} ==="
        )
        print(rendered)
        print()


if __name__ == "__main__":
    main()
