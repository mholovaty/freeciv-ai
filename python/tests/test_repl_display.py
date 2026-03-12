import asyncio

import freeciv_ai.repl as repl


class _DummyClient:
    map_topology_id = 0

    def get_cities(self) -> list[dict]:
        return []

    def get_units(self) -> list[dict]:
        return []


def test_render_display_view_centers_map_vertically(monkeypatch):
    monkeypatch.setattr(repl, "cities_panel_lines", lambda cities: ["C1", "C2"])
    monkeypatch.setattr(repl, "units_panel_lines", lambda units: ["U1", "U2"])
    monkeypatch.setattr(repl, "_render_current_map", lambda client, cols, rows: "M1\nM2\nM3")

    rendered = repl._render_display_view(_DummyClient(), cols=40, rows=7)
    lines = rendered.splitlines()

    assert len(lines) == 7
    assert "M1" not in lines[0]
    assert "M1" not in lines[1]
    assert "M1" in lines[2]
    assert "M2" in lines[3]
    assert "M3" in lines[4]
    assert "C1" in lines[0]
    assert "C2" in lines[1]
    assert "U1" in lines[3]
    assert "U2" in lines[4]
    assert "Map Legend" not in rendered


class _MapClient:
    map_width = 8
    map_height = 6
    map_topology_id = 3
    map_wrap_id = 0

    def get_units(self) -> list[dict]:
        return [{"x": 2, "y": 1, "type": "Settlers"}]

    def get_map(self) -> list[dict]:
        return [{"x": 2, "y": 1, "known": 2, "terrain": "grassland", "n_units": 1, "city_id": -1}]

    def get_cities(self) -> list[dict]:
        return []


def test_render_current_map_initializes_center_from_units(monkeypatch):
    client = _MapClient()
    repl._map_center = None

    def fake_init_map_center(init_client):
        assert init_client is client
        repl._map_center = (11, 22)

    captured: dict[str, object] = {}

    monkeypatch.setattr(repl, "_init_map_center", fake_init_map_center)
    monkeypatch.setattr(
        repl,
        "render_isohex_centered",
        lambda tiles, units, map_width, map_height, gui_col_center, gui_row_center, cols, rows, topology_id, wrap_x, wrap_y: (
            captured.update(
                {
                    "center": (gui_col_center, gui_row_center),
                    "units": units,
                    "tiles": tiles,
                    "dims": (map_width, map_height, cols, rows, topology_id, wrap_x, wrap_y),
                }
            )
            or "rendered"
        ),
    )

    assert repl._render_current_map(client, 40, 12) == "rendered"
    assert captured["center"] == (11, 22)
    assert len(captured["units"]) == 1


class _WrappedIsoHexClient:
    map_width = 32
    map_height = 20
    map_topology_id = 3
    map_wrap_id = 3

    def get_units(self) -> list[dict]:
        return [{"x": 17, "y": 9, "type": "Settlers"}]


def test_wrapped_avg_preserves_signed_gui_coordinate():
    assert repl._wrapped_avg([-54], 120) == -54
    assert repl._wrapped_avg([1, -1], 120) == 0


def test_init_map_center_keeps_signed_topo3_gui_coords():
    client = _WrappedIsoHexClient()
    repl._map_center = None

    repl._init_map_center(client)

    assert repl._map_center == (48, 52)


class _MoveClient:
    map_topology_id = 3

    def get_units(self) -> list[dict]:
        return [{"id": 104, "x": 10, "y": 10, "moves_left": 3}]


def test_cmd_move_rejects_invalid_topo3_direction(capsys):
    repl.cmd_move(_MoveClient(), ["104", "NE"])
    out = capsys.readouterr().out
    assert "Direction NE is invalid on this topology." in out
    assert "Use: NW N E SE S W" in out


class _LegendClient:
    def get_action_decision(self):
        return None


def test_map_command_prints_current_map(monkeypatch, capsys):
    monkeypatch.setattr(repl, "_render_current_map", lambda client, cols, rows: "M1\nM2")

    assert asyncio.run(repl._dispatch_command(_LegendClient(), repl._AIState(), "map"))

    out = capsys.readouterr().out
    assert "M1" in out
    assert "M2" in out


def test_map_legend_command_prints_legend(monkeypatch, capsys):
    monkeypatch.setattr(
        repl,
        "map_legend",
        lambda: "=== Map Legend ===\n\x1b[31mA\x1b[0m  \x1b[32mB\x1b[0m",
    )

    assert asyncio.run(repl._dispatch_command(_LegendClient(), repl._AIState(), "map legend"))

    out = capsys.readouterr().out
    assert "=== Map Legend ===" in out
    assert "\x1b[31mA\x1b[0m  \x1b[32mB\x1b[0m" in out


def test_map_command_rejects_old_argument_forms(capsys):
    assert asyncio.run(repl._dispatch_command(_LegendClient(), repl._AIState(), "map center 1 2"))

    out = capsys.readouterr().out
    assert "Usage: map | map legend" in out
