import argparse

import pytest

from gen_map_examples import _auto_viewport, _default_center, _server_tiles, _validate_topology_args
from freeciv_ai.map_renderer import _tile_layout, map_pos_to_native


def test_server_tiles_topo2_are_rectangular():
    tiles = _server_tiles(2, 3, 3)

    assert len(tiles) == 9
    assert {(t["x"], t["y"]) for t in tiles} == {
        (0, 0), (1, 0), (2, 0),
        (0, 1), (1, 1), (2, 1),
        (0, 2), (1, 2), (2, 2),
    }


def test_server_tiles_topo3_match_native_server_positions():
    tiles = _server_tiles(3, 3, 4)

    native_positions = {
        map_pos_to_native(t["x"], t["y"], 3)
        for t in tiles
    }

    assert len(tiles) == 12
    assert native_positions == {
        (nx, ny)
        for ny in range(4)
        for nx in range(3)
    }


def test_server_tiles_topo3_reject_odd_height():
    try:
        _server_tiles(3, 3, 3)
    except ValueError as exc:
        assert "height must be even" in str(exc)
    else:
        raise AssertionError("expected odd isometric height to be rejected")


def test_validate_topology_args_rejects_unreal_iso_center():
    parser = argparse.ArgumentParser()

    with pytest.raises(SystemExit):
        _validate_topology_args(parser, 3, 3, 4, (0, 0), None, None)


def test_default_viewport_fits_full_topo3_map():
    tiles = _server_tiles(3, 3, 4)
    gui_col_center, gui_row_center = _default_center(3, tiles)
    vcols, vrows = _auto_viewport(3, tiles)

    layout = _tile_layout(
        tiles,
        3,
        4,
        3,
        gui_col_center,
        gui_row_center,
        vcols,
        vrows,
        wrap_x=False,
        wrap_y=False,
    )

    assert len(layout) == len(tiles)
