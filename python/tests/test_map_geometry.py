"""
Unit tests for map_renderer._gui_pos geometry.

Tests are grouped by what they actually prove:
  - STRUCTURAL: derived from first principles, catch wrong axis/formula shape
  - STEP: exact Δgc/Δgr between neighbors, catch wrong step magnitudes
  - PERIOD: _gui_col_wrap_period/_gui_row_wrap_period must agree with _gui_pos arithmetic
  - COLLISION: distinct MAP tiles must produce distinct GUI positions
  - KNOWN: hardcoded (gui_col, gui_row) — note these are derived FROM the formula
    in our heads, so they only catch transcription errors, not conceptual ones

Fair warning: the KNOWN tests will always pass if the implementation is
internally consistent but wrong (because we computed expected values from
the same mental model as the code). The STRUCTURAL tests are more reliable.
"""

import pytest
from freeciv_ai.map_renderer import _gui_pos, _gui_col_wrap_period, _gui_row_wrap_period, _tile_layout


# ---------------------------------------------------------------------------
# STRUCTURAL — axis independence and stagger shape
# These are derived from geometry, not from the code.
# ---------------------------------------------------------------------------

class TestTopo0Structure:
    def test_gc_independent_of_my(self):
        """flat-sq: gc = mx*7, must not depend on my."""
        for my in range(5):
            assert _gui_pos(3, my, 0)[0] == 21

    def test_gr_independent_of_mx(self):
        """flat-sq: gr = my*3, must not depend on mx."""
        for mx in range(5):
            assert _gui_pos(mx, 2, 0)[1] == 6


class TestTopo1Structure:
    def test_gc_depends_on_both_axes(self):
        """iso-sq: gc = (mx-my)*7 — changes when either axis changes."""
        gc00 = _gui_pos(0, 0, 1)[0]
        assert _gui_pos(1, 0, 1)[0] != gc00
        assert _gui_pos(0, 1, 1)[0] != gc00

    def test_diagonal_tiles_share_gc(self):
        """iso-sq: (n,0) and (n+1,1) have same gc because (mx-my) is equal."""
        for n in range(4):
            assert _gui_pos(n, 0, 1)[0] == _gui_pos(n + 1, 1, 1)[0]

    def test_diagonal_tiles_share_gr(self):
        """iso-sq: (n,0) and (0,n) have same gr because (mx+my) = n in both."""
        for n in range(4):
            assert _gui_pos(n, 0, 1)[1] == _gui_pos(0, n, 1)[1]


class TestTopo2Structure:
    """
    Flat-hex geometry invariants.

    The correct layout: columns are vertical, odd columns shifted DOWN.
      - gc depends only on mx (not my) → columns are pure vertical stripes
      - Odd column gr is 2 MORE than even column at same my
      - Within one column, gr increases by 4 per row
    """

    def test_gc_independent_of_my(self):
        """gc = mx*6: changing my must not change gc (columns are vertical)."""
        for my in range(6):
            assert _gui_pos(0, my, 2)[0] == 0,  f"my={my}: even col gc shifted"
            assert _gui_pos(1, my, 2)[0] == 6,  f"my={my}: odd col gc shifted"
            assert _gui_pos(2, my, 2)[0] == 12, f"my={my}: even col gc shifted"

    def test_odd_column_shifted_down_by_2(self):
        """Odd columns should have gr 2 MORE than even columns at same my."""
        for my in range(5):
            gr_even = _gui_pos(0, my, 2)[1]  # column 0, even
            gr_odd  = _gui_pos(1, my, 2)[1]  # column 1, odd
            assert gr_odd - gr_even == 2, f"my={my}: stagger is {gr_odd - gr_even}, want 2"

    def test_even_columns_not_staggered(self):
        """Even columns have no stagger — gr at (0,my) == gr at (2,my)."""
        for my in range(5):
            assert _gui_pos(0, my, 2)[1] == _gui_pos(2, my, 2)[1]
            assert _gui_pos(2, my, 2)[1] == _gui_pos(4, my, 2)[1]

    def test_row_step_within_column(self):
        """Within same column, gr increases by exactly 4 per row."""
        for mx in [0, 1, 2, 3]:
            for my in range(4):
                delta = _gui_pos(mx, my + 1, 2)[1] - _gui_pos(mx, my, 2)[1]
                assert delta == 4, f"mx={mx}, my={my}: row step is {delta}, want 4"

    def test_column_gc_step(self):
        """gc increases by exactly 6 per column."""
        for mx in range(5):
            assert _gui_pos(mx + 1, 0, 2)[0] - _gui_pos(mx, 0, 2)[0] == 6


class TestTopo3Structure:
    def test_gc_depends_on_both_axes(self):
        """iso-hex: gc = (mx-my)*6 — both axes contribute."""
        assert _gui_pos(1, 0, 3)[0] != _gui_pos(0, 0, 3)[0]
        assert _gui_pos(0, 1, 3)[0] != _gui_pos(0, 0, 3)[0]

    def test_same_diagonal_share_gc(self):
        """iso-hex: (n,0) and (n+1,1) same gc because mx-my unchanged."""
        for n in range(4):
            assert _gui_pos(n, 0, 3)[0] == _gui_pos(n + 1, 1, 3)[0]

    def test_antidiagonal_share_gr(self):
        """iso-hex: (n,0) and (0,n) same gr because mx+my = n in both."""
        for n in range(4):
            assert _gui_pos(n, 0, 3)[1] == _gui_pos(0, n, 3)[1]


# ---------------------------------------------------------------------------
# STEP — exact Δgc / Δgr for one-step moves
# ---------------------------------------------------------------------------

class TestSteps:
    def test_topo0_east(self):
        assert _gui_pos(1, 0, 0)[0] - _gui_pos(0, 0, 0)[0] == 7
        assert _gui_pos(1, 0, 0)[1] - _gui_pos(0, 0, 0)[1] == 0

    def test_topo0_south(self):
        assert _gui_pos(0, 1, 0)[0] - _gui_pos(0, 0, 0)[0] == 0
        assert _gui_pos(0, 1, 0)[1] - _gui_pos(0, 0, 0)[1] == 3

    def test_topo1_east(self):
        # E = (mx+1,my): Δgc=+7, Δgr=+3
        assert _gui_pos(1, 0, 1)[0] - _gui_pos(0, 0, 1)[0] == 7
        assert _gui_pos(1, 0, 1)[1] - _gui_pos(0, 0, 1)[1] == 3

    def test_topo1_south(self):
        # S = (mx,my+1): Δgc=-7, Δgr=+3
        assert _gui_pos(0, 1, 1)[0] - _gui_pos(0, 0, 1)[0] == -7
        assert _gui_pos(0, 1, 1)[1] - _gui_pos(0, 0, 1)[1] == 3

    def test_topo2_east_from_even_col(self):
        # Even→Odd column: Δgc=+6, Δgr=+2 (odd col is lower)
        dgc = _gui_pos(1, 0, 2)[0] - _gui_pos(0, 0, 2)[0]
        dgr = _gui_pos(1, 0, 2)[1] - _gui_pos(0, 0, 2)[1]
        assert dgc == 6
        assert dgr == 2

    def test_topo2_east_from_odd_col(self):
        # Odd→Even column: Δgc=+6, Δgr=-2 (even col is higher)
        dgc = _gui_pos(2, 0, 2)[0] - _gui_pos(1, 0, 2)[0]
        dgr = _gui_pos(2, 0, 2)[1] - _gui_pos(1, 0, 2)[1]
        assert dgc == 6
        assert dgr == -2

    def test_topo2_south(self):
        # S = (mx,my+1): Δgc=0, Δgr=+4
        assert _gui_pos(0, 1, 2)[0] - _gui_pos(0, 0, 2)[0] == 0
        assert _gui_pos(0, 1, 2)[1] - _gui_pos(0, 0, 2)[1] == 4

    def test_topo3_east(self):
        # E = (mx+1,my): Δgc=+6, Δgr=+2
        assert _gui_pos(1, 0, 3)[0] - _gui_pos(0, 0, 3)[0] == 6
        assert _gui_pos(1, 0, 3)[1] - _gui_pos(0, 0, 3)[1] == 2

    def test_topo3_south(self):
        # S = (mx,my+1): Δgc=-6, Δgr=+2
        assert _gui_pos(0, 1, 3)[0] - _gui_pos(0, 0, 3)[0] == -6
        assert _gui_pos(0, 1, 3)[1] - _gui_pos(0, 0, 3)[1] == 2


# ---------------------------------------------------------------------------
# PERIOD — _gui_col_wrap_period and _gui_row_wrap_period must match _gui_pos arithmetic
# ---------------------------------------------------------------------------

class TestPeriodConsistency:
    """
    The period helpers must agree with what _gui_pos actually produces.
    Fails if the period comment says 8 but the formula uses 6, etc.
    """

    @pytest.mark.parametrize("topo", [0, 2])
    @pytest.mark.parametrize("W", [4, 6, 8])
    def test_x_period(self, topo, W):
        for mx in range(3):
            for my in range(3):
                gc0 = _gui_pos(mx,     my, topo)[0]
                gc1 = _gui_pos(mx + W, my, topo)[0]
                assert gc1 - gc0 == _gui_col_wrap_period(topo, W), (
                    f"topo={topo} W={W} mx={mx} my={my}: "
                    f"formula gives {gc1-gc0}, period says {_gui_col_wrap_period(topo, W)}"
                )

    @pytest.mark.parametrize("topo", [0, 2])
    @pytest.mark.parametrize("H", [4, 6, 8])
    def test_y_period(self, topo, H):
        for mx in range(3):
            for my in range(3):
                gr0 = _gui_pos(mx, my,     topo)[1]
                gr1 = _gui_pos(mx, my + H, topo)[1]
                assert gr1 - gr0 == _gui_row_wrap_period(topo, H), (
                    f"topo={topo} H={H} mx={mx} my={my}: "
                    f"formula gives {gr1-gr0}, period says {_gui_row_wrap_period(topo, H)}"
                )

    @pytest.mark.parametrize("topo", [1, 3])
    @pytest.mark.parametrize("W", [4, 6, 8])
    def test_iso_x_period(self, topo, W):
        for mx in range(3):
            for my in range(3):
                gc0, gr0 = _gui_pos(mx, my, topo)
                gc1, gr1 = _gui_pos(mx + W, my - W, topo)
                assert gc1 - gc0 == _gui_col_wrap_period(topo, W)
                assert gr1 == gr0

    @pytest.mark.parametrize("topo", [1, 3])
    @pytest.mark.parametrize("H", [4, 6, 8])
    def test_iso_y_period(self, topo, H):
        for mx in range(3):
            for my in range(3):
                gc0, gr0 = _gui_pos(mx, my, topo)
                gc1, gr1 = _gui_pos(mx + H // 2, my + H // 2, topo)
                assert gc1 == gc0
                assert gr1 - gr0 == _gui_row_wrap_period(topo, H)


# ---------------------------------------------------------------------------
# COLLISION — all tiles in a grid must map to distinct GUI positions
# ---------------------------------------------------------------------------

class TestNoCollision:
    @pytest.mark.parametrize("topo", [0, 1, 2, 3])
    def test_distinct_positions(self, topo):
        W, H = 8, 6
        positions = [_gui_pos(x, y, topo) for y in range(H) for x in range(W)]
        assert len(positions) == len(set(positions)), (
            f"topo={topo}: some tiles map to the same GUI position"
        )


# ---------------------------------------------------------------------------
# KNOWN — hardcoded expected values
# NOTE: derived from the formula mentally, not from external ground truth.
# Catch transcription errors but not conceptual bugs.
# ---------------------------------------------------------------------------

class TestKnownValues:
    def test_topo0(self):
        assert _gui_pos(0, 0, 0) == (0, 0)
        assert _gui_pos(1, 0, 0) == (7, 0)
        assert _gui_pos(0, 1, 0) == (0, 3)
        assert _gui_pos(3, 2, 0) == (21, 6)

    def test_topo1(self):
        assert _gui_pos(0, 0, 1) == (0, 0)
        assert _gui_pos(1, 0, 1) == (7, 3)
        assert _gui_pos(0, 1, 1) == (-7, 3)
        assert _gui_pos(2, 2, 1) == (0, 12)

    def test_topo2(self):
        assert _gui_pos(0, 0, 2) == (0, 0)
        assert _gui_pos(1, 0, 2) == (6, 2)   # odd col: gc=6, gr=0+2
        assert _gui_pos(2, 0, 2) == (12, 0)  # even col: gc=12, gr=0+0
        assert _gui_pos(0, 1, 2) == (0, 4)   # same col, next row
        assert _gui_pos(1, 1, 2) == (6, 6)   # odd col, next row: gr=4+2
        assert _gui_pos(3, 1, 2) == (18, 6)  # col 3 (odd), row 1

    def test_topo3(self):
        assert _gui_pos(0, 0, 3) == (0, 0)
        assert _gui_pos(1, 0, 3) == (6, 2)
        assert _gui_pos(0, 1, 3) == (-6, 2)
        assert _gui_pos(1, 1, 3) == (0, 4)
        assert _gui_pos(2, 1, 3) == (6, 6)


# ---------------------------------------------------------------------------
# TILE LAYOUT — pure coordinate mapping
# ---------------------------------------------------------------------------

def _make_tiles(W: int, H: int) -> list[dict]:
    return [{"x": x, "y": y} for y in range(H) for x in range(W)]


class TestTileLayout:
    """Tests for the pure _tile_layout coordinate function."""

    @pytest.mark.parametrize("topo,vcols,vrows", [
        (0, 80, 24), (1, 80, 24), (2, 80, 24), (3, 80, 24),
    ])
    def test_center_tile_placement(self, topo, vcols, vrows):
        """The tile under the center GUI coords must land at canvas (vcols//2-4, vrows//2-2)."""
        W, H = 8, 8
        cx, cy = W // 2, H // 2
        gui_col_center, gui_row_center = _gui_pos(cx, cy, topo)
        tiles = _make_tiles(W, H)
        layout = _tile_layout(tiles, W, H, topo, gui_col_center, gui_row_center, vcols, vrows, wrap_x=False, wrap_y=False)
        assert (cx, cy) in layout, f"topo={topo}: center tile not in layout"
        expected = (vcols // 2 - 4, vrows // 2 - 2)
        assert layout[(cx, cy)] == expected, (
            f"topo={topo}: center tile at {layout[(cx, cy)]}, want {expected}"
        )

    @pytest.mark.parametrize("topo", [0, 1, 2, 3])
    def test_clipping(self, topo):
        """Canvas positions stay within the algorithm's border buffer bounds.

        Tiles at the edge may get canvas_col as negative as -gui_col_tile_step (their
        right side is still visible); this is intentional and handled by MapCanvas.put().
        No tile should land completely outside the extended bounds.
        """
        W, H = 8, 8
        cx, cy = W // 2, H // 2
        gui_col_center, gui_row_center = _gui_pos(cx, cy, topo)
        vcols, vrows = 60, 20
        gui_col_tile_step = 6 if topo in (2, 3) else 7
        cell_half_height = 2
        tiles = _make_tiles(W, H)
        layout = _tile_layout(tiles, W, H, topo, gui_col_center, gui_row_center, vcols, vrows, wrap_x=False, wrap_y=False)
        for (mx, my), (canvas_col, canvas_row) in layout.items():
            assert -gui_col_tile_step <= canvas_col < vcols, f"topo={topo} tile ({mx},{my}): canvas_col={canvas_col} out of [{-gui_col_tile_step},{vcols})"
            assert -cell_half_height <= canvas_row < vrows, f"topo={topo} tile ({mx},{my}): canvas_row={canvas_row} out of [{-cell_half_height},{vrows})"

    @pytest.mark.parametrize("topo", [0, 1, 2, 3])
    def test_no_duplicate_canvas_positions(self, topo):
        """No two tiles should map to the same canvas position."""
        W, H = 8, 8
        cx, cy = W // 2, H // 2
        gui_col_center, gui_row_center = _gui_pos(cx, cy, topo)
        tiles = _make_tiles(W, H)
        layout = _tile_layout(tiles, W, H, topo, gui_col_center, gui_row_center, 80, 24, wrap_x=False, wrap_y=False)
        positions = list(layout.values())
        assert len(positions) == len(set(positions)), f"topo={topo}: duplicate canvas positions"

    def test_wrap_x(self):
        """With wrap_x, a tile at x=0 centered on x=W-1 should appear in layout."""
        W, H = 8, 8
        topo = 0
        # Center on rightmost column
        cx, cy = W - 1, H // 2
        gui_col_center, gui_row_center = _gui_pos(cx, cy, topo)
        tiles = _make_tiles(W, H)
        layout_wrap = _tile_layout(tiles, W, H, topo, gui_col_center, gui_row_center, 80, 24, wrap_x=True, wrap_y=False)
        # x=0 tiles should appear with wrap but may not without wrap
        x0_tiles_wrap = [(mx, my) for (mx, my) in layout_wrap if mx == 0]
        assert len(x0_tiles_wrap) > 0, "wrap_x=True: x=0 tiles should appear near right edge"
        # With wrap, x=0 tiles must appear to the right of center (canvas_col > 4)
        for key in x0_tiles_wrap:
            assert layout_wrap[key][0] > 4, f"x=0 tile {key} should be right of center with wrap"

    def test_topo3_wrap_x_preserves_gui_row(self):
        W, _ = 16, 24
        topo = 3
        base = _gui_pos(4, 12, topo)
        wrapped = _gui_pos(4 + W, 12 - W, topo)
        assert wrapped[0] - base[0] == _gui_col_wrap_period(topo, W)
        assert wrapped[1] == base[1]
