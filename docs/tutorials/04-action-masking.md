# Tutorial 04 — Action Masking: Teaching the Agent What Is Possible

This tutorial explains **action masking** — what it is, why it matters, and exactly how it is implemented across the Freeciv AI codebase.

---

## 1. The Problem: Moving Into Walls

After a few training episodes you will notice the agent frequently tries to move into ocean tiles, mountains, or off the map edge — and gets "blocked". This is not a flaw in the reward function. It is a flaw in what information the agent has.

### What the model sees (before this fix)

The observation vector contains:
- Per-tile: `known` status — `0.0` (unseen), `0.5` (fogged), `1.0` (visible)
- Per-unit: `x / map_w`, `y / map_h`, `moves_left / moves_max`

**Crucially, there is no terrain information.** Ocean and grassland look identical in the observation. The model cannot learn "SW is ocean" because it literally cannot see the difference between ocean and grassland. All it knows is "I tried SW and nothing moved" — but that gradient signal is weak and slow.

### The wasted gradient

Without masking, the training loop proceeds like this every time a unit tries to walk into the sea:

1. Model outputs high probability for SW direction
2. `env.step()` calls `can_do_action` → blocked → no `do_action` call issued
3. The unit doesn't move, no tiles are revealed
4. Reward is just the step penalty: `−0.01`
5. Policy gradient says: "SW was a bad action, reduce its probability"

This works eventually — the agent will learn to avoid blocked directions through trial and error. But it is slow, noisy, and means the model wastes capacity learning constraints that could simply be *told* to it.

---

## 2. The Solution: Action Masking

**Action masking** removes impossible actions from the distribution before sampling. The model never samples a blocked action — it only chooses from what the server says is legal.

```
without masking:          with masking:
logits = [2.1, 0.8, -0.3, 1.5, ...]    logits = [2.1, 0.8, -inf, 1.5, ...]
                                                          ↑
                                              (SW is ocean — set to -inf)

softmax → [0.41, 0.18, 0.06, 0.30, ...]  softmax → [0.46, 0.20,  0.0, 0.34, ...]
                                                               ↑
                                                          zero probability
```

Setting a logit to `-inf` before softmax gives that action exactly **zero probability**. It cannot be sampled. The distribution is renormalised over only the valid actions.

### Why `-inf` and not just clamping?

`Categorical(logits=logits)` applies `log_softmax` internally. `exp(-inf) = 0`, so the action's probability is exactly zero. Other approaches (e.g. setting to a large negative number like `-1e9`) could leave tiny residual probability and cause numerical issues in `log_prob`. Using `-inf` is mathematically exact.

### What about entropy?

The entropy bonus in REINFORCE is `mean entropy across all distributions`. When some actions are masked, the entropy of those distributions is computed only over valid actions — which is correct. The model is rewarded for exploring among *reachable* options, not for randomly attempting blocked moves.

---

## 3. The Mask Tensor

The mask is a `(max_units, 9)` boolean tensor, one row per unit slot:

| Index | Meaning | Always valid? |
|-------|---------|---------------|
| 0     | Skip    | Yes           |
| 1     | Move N  | If `can_do_action` ≥ 0 for any UNIT_MOVE variant |
| 2     | Move NE | Same |
| 3     | Move E  | Same |
| 4     | Move SE | Same |
| 5     | Move S  | Same |
| 6     | Move SW | Same |
| 7     | Move W  | Same |
| 8     | Move NW | Same |

`True` = action is valid and may be sampled. `False` = action is illegal; logit will be set to `-inf`.

Skip (action 0) is always `True` — a unit can always choose to do nothing.

For unit slots beyond the actual number of units (padding), all entries are `False` except skip. Since the policy head always operates on `n_units` rows, these padding rows are trimmed before any distribution is constructed — but the mask preserves the same shape for safe `torch.stack` across timesteps.

---

## 4. Implementation: `_make_action_mask` in `env.py`

```python
def _make_action_mask(client, units, max_units):
    mask = torch.zeros(max_units, 9, dtype=torch.bool)
    mask[:, 0] = True                          # skip always valid

    for i, u in enumerate(units[:max_units]):
        uid, x, y = u["id"], u["x"], u["y"]
        for d in range(8):                     # directions 0=N .. 7=NW
            tx, ty = _dir_to_tile(x, y, d)
            tidx = client.tile_index(tx, ty)
            if tidx < 0:
                continue                       # off-map edge → stays False
            for act in (UNIT_MOVE, UNIT_MOVE2, UNIT_MOVE3):
                if client.can_do_action(uid, act, tidx) >= 0:
                    mask[i, d + 1] = True      # at least one variant works
                    break
    return mask
```

Key points:

- **Off-map edges** (`tidx < 0`) stay `False` — the unit simply cannot go there.
- **Three move variants** are tried in order. Freeciv distinguishes `UNIT_MOVE`, `UNIT_MOVE2`, `UNIT_MOVE3` for different movement cost regimes. A direction is valid if *any* variant succeeds.
- **`moves_left == 0`**: `can_do_action` will return `< 0` for all directions when a unit has no movement points left, so only skip will be valid. This integrates naturally with the multi-step movement loop in `repl.py`.
- **`can_do_action` is authoritative** — it queries the C library's action system which applies all Freeciv rules: terrain passability, ZOC, unit type restrictions, etc. No game-logic is reimplemented in Python.

The function is defined **before** the `FreecivEnv` class so it can be used inside class methods without forward-reference issues, and exported for use in `repl.py` and `play.py`.

---

## 5. Where the Mask Flows

### `FreecivEnv` (training)

`reset()` and `step()` both call `_make_action_mask` immediately after refreshing `last_units`:

```python
self.last_units = client.get_units()[:self.max_units]
self.last_mask  = _make_action_mask(client, self.last_units, self.max_units)
```

The mask is always in sync with the units — if a unit moves, its position changes, and the next mask reflects the new neighbours.

### `_run_episode` in `train.py` (collecting trajectories)

```python
mask = env.last_mask                              # valid actions this step
acts, _ = policy.select_actions(obs, n_units, mask)
next_obs, reward, done, info = await env.step(acts)
observations.append(obs)
masks.append(mask)                                # stored for training update
```

The mask is collected alongside observations and actions. It is needed again during the update step to recompute log-probabilities consistently.

### `_update` in `train.py` (gradient computation)

```python
masks_batch = torch.stack(masks)                  # (T, max_units, 9)
log_probs, values, entropy = policy.evaluate_actions(
    obs_batch, acts_padded[:, :n_units], n_units, masks_batch
)
```

The same mask that was used during sampling is reapplied during the policy update. This is critical for correctness: if the mask had changed between sampling and update, the log-probability of the sampled action could be computed under a different distribution than the one that generated it, invalidating the policy gradient.

### `model.py` — applying the mask in `forward()`

```python
logits = self.policy_head(features)
logits = logits.view(*obs.shape[:-1], self.max_units, N_ACTIONS)
logits = logits[..., :n_units, :]

if action_mask is not None:
    mask = action_mask[..., :n_units, :]
    logits = logits.masked_fill(~mask, float("-inf"))
```

`masked_fill(~mask, -inf)` fills positions where `mask == False` with `-inf`. The `~` operator inverts the boolean tensor. This runs entirely on the same device as the logits tensor (CPU or GPU) with no Python loop.

### `repl.py` and `play.py` (inference)

Both compute the mask fresh before each `select_actions` call using the current unit states:

```python
mask = _make_action_mask(client, obs_units, ai.max_units)
actions, _ = ai.policy.select_actions(obs, n_units, mask)
```

At inference the mask is not stored — it is only needed for this one sampling call.

---

## 6. Training Implications

### Cleaner gradient signal

Before masking, the model received gradient signal for blocked actions. The policy gradient said "you moved into ocean and got -0.01, so reduce that probability". With masking, blocked actions are never sampled, so the model only receives gradient signal about *what actually happened* — the choice among valid options.

This means:
- Faster convergence: the model is not wasting capacity learning terrain passability from scratch
- Less noisy gradients: every sampled action led to an observable outcome
- Better exploration: entropy bonus now applies only to reachable actions, so the model explores directional diversity within the valid set rather than uniformly across all 9 actions including unreachable ones

### Checkpoint compatibility

The model architecture is **unchanged** — `action_mask` is an optional parameter with default `None`. Old checkpoints remain loadable. However, a model trained without masking will have miscalibrated logits for blocked directions (they may be high), which will initially cause the masked distribution to concentrate on the few valid actions in unexpected ways. **Retraining from scratch is recommended.**

### What if all directions are blocked?

If a unit is surrounded by impassable terrain (rare but possible), only skip (action 0) is valid. The distribution degenerates to a point mass on skip, entropy is 0 for that unit, and it contributes no gradient signal. This is correct behaviour — there is genuinely nothing useful to learn when all moves are blocked.

---

## 7. TODO — Option B: Terrain in the Observation

Action masking solves the **sampling problem** (the model never picks invalid actions) but does not give the model *spatial awareness* of terrain. The model still cannot plan a path around an ocean bay because it has no representation of which tiles are water vs land.

**What to add:** a second map layer in the observation vector encoding terrain passability (or terrain type) for each tile. Concretely:

- Alongside the existing `known` map layer (size `map_w × map_h`), add a `passable` layer of the same size: `1.0` if a land unit can enter, `0.0` if not, and `0.5` (or `0.0`) for unknown tiles.
- The observation size grows from `map_w × map_h + max_units × 3` to `2 × map_w × map_h + max_units × 3`.
- The model architecture changes: `obs_size` increases, so the first `Linear` layer in the trunk must be rebuilt. Old checkpoints become **incompatible** (different input size).

**Why this matters:** with terrain in the observation, the model can learn that moving toward a coast eventually leads to a dead end and start preferring inland directions earlier. It enables multi-step planning through the value function — the agent can "see" that a direction leads into water before trying it.

**Implementation notes:**
- Populate the terrain layer in `FreecivEnv._make_obs()` and in `_make_obs_for_client()` in `repl.py`.
- A tile with `known == 0` (never seen) has unknown terrain — encode as `0.0` (neutral / assume not passable) or as a separate third value (extend to a 3-value encoding: unknown / passable / impassable).
- Terrain is available from `client.get_map()` via the `terrain` field (a string like `"Grassland"`, `"Ocean"`, `"Mountains"`, etc.). Land units can generally enter: Grassland, Plains, Forest, Hills, Jungle, Swamp, Desert, Tundra, Arctic (with cost). They cannot enter: Ocean, Lake, Glacier (impassable without special unit).
- A clean approach: query `can_do_action` for a hypothetical move onto each tile type once at game start to build a static `terrain_name → passable` lookup, then use that to populate the layer from `t["terrain"]` without calling `can_do_action` for every tile every turn.

**When to do this:** after the action-masked model has been trained and validated. The reward signal should show a clear improvement first. Then add terrain features, retrain from scratch (new obs size), and compare.

---

## Next Steps

- **Tutorial 05** (planned): Replace REINFORCE with PPO for better sample efficiency and stability.
- **Tutorial 06** (planned): Add a CNN over the map instead of a flat MLP for spatial reasoning — natural complement to the terrain observation layer.
