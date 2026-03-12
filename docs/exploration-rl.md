# Tutorial — Training an Exploration Agent with REINFORCE

This tutorial explains every building block used in the Freeciv exploration training pipeline. It is intended as a self-contained reference for the code in `python/freeciv_ai/torch/`.

---

## 1. Reinforcement Learning Basics

In **Reinforcement Learning (RL)** an **agent** interacts with an **environment** in a loop:

```
agent ──action──► environment
      ◄──observation, reward──
```

| Concept | Definition |
|---------|-----------|
| **State / Observation** | What the agent sees at each timestep |
| **Action** | What the agent chooses to do |
| **Reward** | A scalar signal indicating how good the action was |
| **Episode** | A complete sequence from start to termination |
| **Policy π** | A mapping from observation → probability distribution over actions |
| **Value V(s)** | Expected total future reward starting from state *s* |

The agent's goal is to maximise the total **discounted return**:

```
G_t = r_t + γ·r_{t+1} + γ²·r_{t+2} + ...
```

where **γ ∈ [0, 1]** (gamma) is the discount factor — rewards sooner are worth more than rewards later.

---

## 2. The Environment — `FreecivEnv`

`FreecivEnv` (`freeciv_ai/torch/env.py`) wraps the Freeciv game into the standard RL interface:

```python
obs = await env.reset()                     # start a game
obs, reward, done, info = await env.step(actions)  # advance one turn
await env.close()                            # shut down the server
```

### Observation

A flat `float32` tensor of size `map_w × map_h + max_units × 3`:

- **Map section** (`map_w × map_h` values): per-tile known status
  `0.0` = never seen, `0.5` = fogged (seen before), `1.0` = currently visible
- **Unit section** (`max_units × 3` values): for each unit slot:
  `x / map_w`, `y / map_h`, `moves_left / moves_max`
  (zero-padded if fewer units than `max_units`)

### Actions

9 discrete actions per unit:

| Index | Meaning           |
|-------|-------------------|
| 0     | Skip (do nothing) |
| 1     | Move North        |
| 2     | Move North-East   |
| 3     | Move East         |
| 4     | Move South-East   |
| 5     | Move South        |
| 6     | Move South-West   |
| 7     | Move West         |
| 8     | Move North-West   |

### Reward

```
reward = (number of newly revealed tiles this turn) − 0.01
```

The `−0.01` per-step penalty discourages the agent from wasting turns without exploring.

### Episode termination

An episode ends after `max_turns` turns (configurable, default 20).

---

## 3. The Policy Network — `ExplorerPolicy`

`ExplorerPolicy` (`freeciv_ai/torch/model.py`) is a PyTorch `nn.Module` — the neural network that *is* the agent's policy.

### Architecture

```
observation (flat vector)
        │
  Linear(obs_size → hidden)  ← shared trunk
        │  ReLU
  Linear(hidden → hidden)
        │  ReLU
       ┌┴──────────────────┐
  policy head           value head
  Linear → max_units×9  Linear → 1
  (action logits)       (state value)
```

### Policy head

Outputs **logits** — unnormalised scores for each of the 9 actions for each unit. Passing logits through **softmax** gives a probability distribution. Sampling from this distribution gives the agent's chosen action.

```python
logits, value = policy(obs, n_units)
dist = Categorical(logits=logits)   # one distribution per unit
action = dist.sample()              # integer in [0, 8]
log_prob = dist.log_prob(action)    # log π(a|s)
```

### Value head

Outputs a single scalar estimating how good the current state is (the baseline). This is *not* used to select actions — only to reduce variance during training.

---

## 4. REINFORCE with Value Baseline

**REINFORCE** is the simplest policy gradient algorithm. The key idea:

> *Increase the probability of actions that led to high return; decrease it for actions that led to low return.*

### Algorithm

For each episode:

1. **Collect** a trajectory `(s_0, a_0, r_0), (s_1, a_1, r_1), ..., (s_T, a_T, r_T)`
2. **Compute** discounted returns: `G_t = Σ_{k≥t} γ^{k-t} · r_k`
3. **Compute** advantage: `A_t = G_t − V(s_t)`
   (how much better was this action than the average?)
4. **Policy loss**: `L_π = −mean( log π(a_t|s_t) · A_t )`
   Minimising this maximises expected return.
5. **Value loss**: `L_V = mean( (G_t − V(s_t))² )`
   Trains the value head to predict returns accurately.
6. **Total loss**: `L = L_π + c_V · L_V − c_H · H`
   where `H = entropy(π)` is added to encourage exploration.

### Why subtract the value (baseline)?

Without a baseline, REINFORCE has high variance — the gradient signal is noisy and training is slow. Subtracting `V(s_t)` does not change the expected gradient (it is unbiased) but significantly reduces variance, making training faster and more stable.

### Gradient clipping

After `loss.backward()`, gradients are clipped to max norm 0.5:

```python
torch.nn.utils.clip_grad_norm_(policy.parameters(), max_norm=0.5)
```

This prevents a single bad episode from causing a destructively large update.

---

## 5. The Training Loop — `train.py`

`freeciv_ai/torch/train.py` ties everything together:

```
for each episode:
    1. env.reset()          → start a new game
    2. collect trajectory   → run until done (FreecivEnv.step in a loop)
    3. compute returns      → _discounted_returns(rewards, gamma)
    4. evaluate_actions()   → log_probs, values, entropy from policy
    5. compute losses       → REINFORCE + value + entropy
    6. optimizer.step()     → update network weights
    7. (every N episodes)   → save checkpoint
```

### Running training

```bash
cd python
python3 -m freeciv_ai.torch.train \
    --episodes 200 \
    --turns 20 \
    --lr 3e-4 \
    --gamma 0.99 \
    --save-every 50 \
    --checkpoint ./checkpoints
```

### Resuming from a checkpoint

```bash
python3 -m freeciv_ai.torch.train \
    --episodes 200 \
    --resume ./checkpoints/ep000050.pt
```

### Key hyperparameters

| Flag | Default | Effect |
|------|---------|--------|
| `--episodes` | 200 | Total training episodes |
| `--turns` | 20 | Max turns per episode (episode length) |
| `--lr` | 3e-4 | Adam learning rate |
| `--gamma` | 0.99 | Discount factor |
| `--value-coef` | 0.5 | Weight of value loss |
| `--entropy-coef` | 0.01 | Weight of entropy bonus |
| `--hidden` | 256 | Hidden layer width |
| `--max-units` | 16 | Units tracked per step |

---

## 6. What to Watch During Training

The training log prints one line per episode:

```
ep   10  return=3.42  loss=0.0812  π=0.0614  V=0.0198  H=2.1543
```

| Field | What it means |
|-------|--------------|
| `return` | Total undiscounted reward this episode — the primary metric |
| `π` (policy_loss) | Should trend downward as the policy improves |
| `V` (value_loss) | Should decrease as the value head learns to predict returns |
| `H` (entropy) | Should stay above ~1.0; if it collapses to 0 the policy has converged prematurely |

A well-training agent will show `return` increasing over episodes, meaning it is discovering more tiles per game.

---

## Next Steps

- **Tutorial**: Scaling the action space — masking, hierarchical actions, and attention-based encodings (`action-space-scaling.md`).
- **Tutorial**: Running a trained agent against a live server (`play.md`).
- **Tutorial**: Action masking — eliminating blocked moves from the policy distribution (`action-masking.md`).
- **Tutorial 05** (planned): Replace REINFORCE with PPO for better sample efficiency.
- **Tutorial 06** (planned): Add a CNN over the map instead of a flat MLP for spatial reasoning.
