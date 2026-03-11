# Tutorial 02 — Scaling the Action Space

This tutorial discusses how the current flat integer action encoding works, where it breaks down as the task grows more complex, and what alternative encodings survive extension without invalidating trained checkpoints or model architecture.

---

## 1. The Current Encoding

`FreecivEnv.step(actions)` takes a list of integers — one per unit — in the range `[0, N_ACTIONS)`:

| Integer | Meaning                     |
|---------|-----------------------------|
| 0       | Skip                        |
| 1–8     | Move in one of 8 directions |

Internally the env translates each integer into a client command:

```
actions[i]  →  unit i (by position in env.last_units)
    0        →  skip
    1–8      →  direction offset → target tile coords → UNIT_MOVE
```

This works well for the exploration task because the action space is small and fixed.

---

## 2. Where Flat Integers Break Down

As the task grows more complex (combat, city founding, diplomacy, trade, …) several problems emerge:

**Re-numbering.** Adding a new action type shifts the meaning of existing integers. Old checkpoints become invalid because the policy head's output indices no longer match the same actions.

**Output size explosion.** The policy head is `Linear(hidden, max_units * N_ACTIONS)`. Every new action type adds `max_units` output neurons. Most of them are invalid most of the time, so the model wastes capacity and gradient signal on unreachable actions.

**Target space growth.** Actions like "attack unit X" or "trade with city Y" require selecting a *specific* entity, not just a direction. The number of valid targets can grow with map size, which a fixed-size head cannot handle.

---

## 3. Approaches That Scale

### 3.1 Action Masking

The simplest improvement — compatible with the current flat encoding.

Before sampling, set logits of invalid actions to `-inf` so they get zero probability after softmax:

```python
logits[invalid_mask] = float('-inf')
dist = Categorical(logits=logits)
action = dist.sample()
```

`FreecivEnv` already validates actions in `step()` via `can_do_action`, but the model still receives gradient signal through invalid actions it sampled. Masking moves the validity check *before* sampling, so the policy only learns from reachable actions.

This is a low-effort improvement to the current architecture and is almost always worth adding.

### 3.2 Hierarchical / Factored Action Space

Decompose one action decision into a sequence of smaller decisions, each with its own small output head:

```
1. select unit        → which unit acts
2. select action type → move / attack / found city / …
3. select target      → direction, tile, or entity
```

Each head is independent. Adding a new action type only affects the action-type head — the unit-selection and target-selection heads are unchanged, and their weights can be reused from an old checkpoint.

This is the approach used by AlphaStar (DeepMind, 2019) for StarCraft II.

### 3.3 Action Embeddings

Instead of `index → meaning`, each action is described by a **learned feature vector**:

```python
action_features = embed(action_type, direction, target_type, ...)
score = dot(state_repr, action_features)        # one score per candidate action
dist  = Categorical(logits=scores)
```

Adding a new action = adding a new embedding row. All existing action embeddings and model weights stay the same, so old checkpoints remain valid. The model generalises across structurally similar actions because they share embedding space.

### 3.4 Pointer / Attention Networks

The most flexible approach. Instead of a fixed set of action indices, generate a **dynamic candidate list** at runtime — each candidate described by its features — and let the model attend over it:

```
candidates = [
    {"type": MOVE, "direction": N,  "features": ...},
    {"type": MOVE, "direction": NE, "features": ...},
    {"type": ATTACK, "target_id": 42, "features": ...},
    ...
]
scores = attention(state_repr, candidate_features)   # shape: (n_candidates,)
action = candidates[argmax(scores)]
```

The action set can change every step (e.g. only list currently valid actions). There is no fixed output size — the model scores whatever candidates exist. This is the standard approach for combinatorial or open-ended action spaces.

---

## 4. Practical Progression for Freeciv

| Stage | Task complexity | Recommended encoding |
|-------|----------------|----------------------|
| Now | Map exploration (movement only) | Flat integers `[0..8]` |
| Next | + action masking | Flat integers + validity mask |
| Later | + new action types (attack, build) | Hierarchical: type head + target head |
| Advanced | + entity targeting across map | Attention / pointer over candidates |

The jump from flat integers to action masking requires only a few lines of change in `model.py` and `env.py`. The jump to hierarchical requires restructuring both the policy head and the `step()` translation logic, but the env–model interface remains a list of sub-decisions rather than a single integer.

---

## Next Steps

- **Tutorial 03**: Running a trained agent against a live server, including multi-agent setups (`03-play.md`).
- **Tutorial 04** (planned): Add a CNN over the map instead of a flat MLP for spatial reasoning.
