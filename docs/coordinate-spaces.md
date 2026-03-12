# Tutorial — Server Coordinates, Map Coordinates, and Display Positions

This tutorial explains how Freeciv coordinates flow from the server to the Python client and finally to the ASCII display.

It covers all four topologies supported by `map_renderer.py`:

- `topo 0` — flat square
- `topo 1` — iso square
- `topo 2` — flat hex
- `topo 3` — iso hex

---

## 1. The Three Coordinate Spaces

There are three different coordinate spaces in play:

### Native coordinates

These are the server's storage coordinates:

- `nx`, `ny`
- rectangular
- size is exactly `map_width x map_height`

This is how Freeciv stores the map internally.

### Map coordinates

These are the gameplay coordinates exposed to Python:

- `x`, `y`
- used by `get_map()`
- used by `get_units()`
- used by `tile_index(x, y)`
- used by movement and action targeting
- used by direction stepping and neighbor logic

When we talk about "tile coordinates" in the Python client, we usually mean these map coordinates.

This is the coordinate space the client-facing API speaks. If Python asks for a
unit position, issues a directional move, or targets a tile, it does so in map
coordinates, not native coordinates.

### GUI coordinates

These are the renderer's projected positions:

- `gui_col`
- `gui_row`

They are not gameplay coordinates. They only decide where a tile is drawn on the terminal canvas.

So the full pipeline is:

`native -> map -> gui -> terminal cells`

---

## 2. Exact Native -> Map Formulas for All Topologies

Let:

- `nx`, `ny` = native coordinates
- `x`, `y` = map coordinates
- `W` = native map width
- `H` = native map height

### Topo 0 — flat square

Native and map coordinates are identical:

```text
x = nx
y = ny
```

Inverse:

```text
nx = x
ny = y
```

### Topo 2 — flat hex

Native and map coordinates are also identical:

```text
x = nx
y = ny
```

Inverse:

```text
nx = x
ny = y
```

So for both flat topologies:

- valid map coordinates are the plain rectangle `0..W-1 x 0..H-1`
- the server's rectangular storage grid is the same as the gameplay grid

### Topo 1 — iso square

Native and map coordinates differ:

```text
x = ((ny + (ny & 1)) // 2) + nx
y = ny - x + W
```

Inverse:

```text
ny = x + y - W
nx = (2*x - ny - (ny & 1)) // 2
```

### Topo 3 — iso hex

Native and map coordinates differ in exactly the same way as `topo 1`:

```text
x = ((ny + (ny & 1)) // 2) + nx
y = ny - x + W
```

Inverse:

```text
ny = x + y - W
nx = (2*x - ny - (ny & 1)) // 2
```

So the exact difference is:

- `topo 0`: `map == native`
- `topo 2`: `map == native`
- `topo 1`: `map` is transformed from native with the isometric formulas above
- `topo 3`: `map` is transformed from native with the same isometric formulas above

---

## 3. What Those Formulas Mean Geometrically

For flat topologies (`topo 0`, `topo 2`), the native rectangle stays a rectangle in map space.

For isometric topologies (`topo 1`, `topo 3`), the same native rectangle becomes a slanted diamond/parallelogram in map space.

That is why isometric maps do **not** appear as a simple `0..W-1 x 0..H-1` rectangle in map coordinates.

For example, in flat topologies a `3x3` map really has these map coordinates:

```text
(0,0) (1,0) (2,0)
(0,1) (1,1) (2,1)
(0,2) (1,2) (2,2)
```

### Example: `topo 3`, `W=3`, `H=4`

Using:

```text
x = ((ny + (ny & 1)) // 2) + nx
y = ny - x + W
```

with `W = 3`, the first few native tiles convert like this:

```text
native (0,0):
  x = ((0 + 0) // 2) + 0 = 0
  y = 0 - 0 + 3 = 3
  -> map (0,3)

native (1,0):
  x = ((0 + 0) // 2) + 1 = 1
  y = 0 - 1 + 3 = 2
  -> map (1,2)

native (2,0):
  x = ((0 + 0) // 2) + 2 = 2
  y = 0 - 2 + 3 = 1
  -> map (2,1)

native (0,1):
  x = ((1 + 1) // 2) + 0 = 1
  y = 1 - 1 + 3 = 3
  -> map (1,3)
```

If you keep doing that for every native tile in the `3x4` rectangle, you get:

The real server tiles are:

```text
(0,3) (1,2) (2,1)
(1,3) (2,2) (3,1)
(1,4) (2,3) (3,2)
(2,4) (3,3) (4,2)
```

Notice that `(0,0)` is not present.

That is why `gen_map_examples.py --topo 3 -W 3 -H 4` does not show tile `00`: it is not a real server tile for that map.

---

## 4. Why Iso Height Must Be Even

Freeciv requires even native height for isometric maps.

In practice:

- `topo 1` and `topo 3` require `map_height % 2 == 0`

That is why `gen_map_examples.py` now rejects commands like:

```bash
python3 gen_map_examples.py --topo 3 -W 3 -H 3
```

The example generator now validates this the same way the real game geometry does.

---

## 5. Map -> GUI Projection for Each Topology

Once the Python client has map coordinates, `map_renderer.py` converts them to GUI positions.

### Topo 0 — flat square

```text
gui_col = mx * 7
gui_row = my * 3
```

Meaning:

- columns stay vertical
- rows stay horizontal

### Topo 1 — iso square

```text
gui_col = (mx - my) * 7
gui_row = (mx + my) * 3
```

Meaning:

- map axes become diagonals on screen
- visually forms a diamond/isometric grid

### Topo 2 — flat hex

```text
gui_col = mx * 6
gui_row = my * 4 + (mx % 2) * 2
```

Meaning:

- columns stay vertical
- odd columns are shifted downward

### Topo 3 — iso hex

```text
gui_col = (mx - my) * 6
gui_row = (mx + my) * 2
```

Meaning:

- the renderer matches Freeciv GTK/client iso-hex projection
- the map axes become diagonal screen axes

This is the topology that the user verified against the GTK observer.

---

## 6. Logical Adjacency vs Screen Appearance

A key point:

**screen alignment does not define gameplay adjacency**

Gameplay uses map coordinates and Freeciv direction rules. The renderer only projects those tiles to the screen.

That also means:

- the coordinates returned by the client are map coordinates
- movement directions are interpreted in map-coordinate space
- `tile_index(x, y)` expects map coordinates
- Python code should only use native coordinates when it is explicitly doing native/map conversion or wrap math

- a visually straight line on screen does not necessarily mean "same logical direction"
- two topologies can show the same logical neighbors in different visual arrangements

This matters especially for hex maps.

### Valid directions on hex maps

For `topo 2` and `topo 3`, each tile still has 6 valid neighbors, but the named direction set depends on the topology:

- `topo 2` invalid: `NW`, `SE`
- `topo 3` invalid: `NE`, `SW`

So `topo 3` movement is not 8-way square movement. It is hex movement in the same form as Freeciv GTK.

---

## 7. Logical Tiles, GUI Space, and Wrap Periods

Before talking about display wrapping, it helps to define three renderer terms precisely.

### Logical tile

A **logical tile** means one actual gameplay tile identified by its map coordinate:

```text
(x, y)
```

This is the tile the server talks about, the tile a unit stands on, and the tile used for movement and actions.

Even on a wrapping map, there is still just one logical tile `(x, y)`.

If that tile can appear at several screen positions because of wrapping, those are not different tiles. They are only different **wrapped copies of the same logical tile**.

### GUI space

**GUI space** is the renderer's 2D projected coordinate system:

```text
(gui_col, gui_row)
```

This is not gameplay space. It only answers:

- where should this tile be drawn horizontally?
- where should this tile be drawn vertically?

`map_renderer.py` first converts each logical tile from map coordinates to GUI space with `_gui_pos()`, and only after that does it place the tile on the terminal canvas.

### Wrap period

A **wrap period** is the GUI-space shift produced by one full wrap around the map.

For example:

- x-wrap period = "how far does the drawn tile move in GUI space when I go once around the x seam?"
- y-wrap period = "how far does the drawn tile move in GUI space when I go once around the y seam?"

These are measured in GUI coordinates, not map coordinates.

That is why `map_renderer.py` exposes:

- `_gui_col_wrap_period()`
- `_gui_row_wrap_period()`

They tell the renderer how far it may shift a tile in GUI space when choosing the best wrapped copy for display.

---

## 8. Wrapping

Wrapping is another place where native vs map coordinates matters.

### Flat topologies

For `topo 0` and `topo 2`, wrapping is simple:

- x-wrap moves along the map x-axis
- y-wrap moves along the map y-axis

### Isometric topologies

For `topo 1` and `topo 3`, Freeciv wraps in **native** space first.

When converted back to map space, the wrap vectors are:

### X-wrap

```text
(mx, my) -> (mx + W, my - W)
```

### Y-wrap

```text
(mx, my) -> (mx + H/2, my + H/2)
```

These are the real wrap moves for isometric maps.

This detail was the root cause of the earlier black-gap bug: Python was initially treating isometric wrap as simple `+W` or `+H` in map space, which is wrong.

---

## 9. How Display Wrapping Chooses What You See

The renderer does **not** duplicate the map into many copies and draw all of them.

Instead, for each logical tile, it chooses the single wrapped copy that is best for the current viewport.

The steps are:

1. Take one logical tile `(x, y)`
2. Convert it to its base GUI position with `_gui_pos()`
3. Use the GUI wrap periods to ask: "if I shift this tile by full-wrap multiples, which copy lands closest to the viewport center?"
4. Draw only that chosen copy

This is why the renderer can:

- keep the map centered correctly on wrapping worlds
- avoid showing multiple copies of the same logical tile
- still make seam-crossing maps look continuous

In code, `_tile_layout()` stores its result keyed by logical tile coordinate:

```text
{(x, y): (canvas_col, canvas_row)}
```

So one logical tile produces at most one canvas position.

That is the key reason already-shown tiles are not repeated as separate tiles.

---

## 10. How `map_renderer.py` Uses This

The renderer receives tiles in map coordinates and does three things:

1. Convert each tile from map coordinates to GUI coordinates
2. Choose the wrapped copy nearest to the viewport center
3. Draw the tile on the ASCII canvas

The important internal helpers are:

- `_gui_pos()` — map -> gui projection
- `_gui_col_wrap_period()` / `_gui_row_wrap_period()` — wrap periods in GUI space
- `_tile_layout()` — decides where each visible tile lands on the canvas

The REPL display and the example generator both eventually go through the same renderer path.

---

## 11. How `gen_map_examples.py` Now Works

The example generator is meant to test display representation, so it now mirrors server behavior more closely.

### For flat topologies

It generates tiles directly as:

```text
(x, y) = (nx, ny)
```

### For isometric topologies

It now:

1. Iterates the native rectangular server grid
2. Converts each native tile to a map coordinate with the Freeciv formula
3. Passes those map coordinates to `render_map_centered()`

That means the example tool now uses the same kind of tile coordinates the real server would expose.

### Default centering

By default it no longer centers on an arbitrary tile.

Instead it:

1. Computes the GUI bounding box of all generated tiles
2. Uses the midpoint of that GUI bounding box as the default center
3. Auto-sizes the viewport to fit that full bounding box

That is why the map is no longer clipped by default.

---

## 12. Practical Rules of Thumb

If you are debugging the client, these are the safest rules:

### Rule 1: Trust map coordinates for gameplay

If the server says a unit is at `(x, y)`, that is the logical tile used for:

- movement
- actions
- visibility
- city placement

### Rule 2: Trust GUI coordinates only for drawing

If a tile lands at a certain `gui_col, gui_row`, that only tells you where it is drawn, not what its logical neighbors are.

### Rule 3: On isometric maps, do not assume `x` is bounded by `map_width`

For `topo 1` and `topo 3`, map coordinates can exceed `map_width - 1` because the rectangular native map has been re-expressed in map space.

### Rule 4: For iso maps, wrapping must be reasoned about in native space

If something looks wrong around seams, think:

`map -> native -> wrap -> map -> gui`

not just:

`map + width`

---

## 13. Summary

- Freeciv stores maps in **native** rectangular coordinates
- Python gameplay APIs expose **map** coordinates
- `map_renderer.py` projects map coordinates into **GUI** positions
- flat topologies keep native == map
- isometric topologies convert native rectangles into map-space diamonds
- isometric wrapping must use native-space wrap vectors
- the example generator now mirrors server-style tile generation and full-map centering

The most important mental model is:

```text
server storage (native) -> gameplay coords (map) -> display placement (gui)
```

If those three spaces are kept distinct, the renderer and movement logic become much easier to reason about.
