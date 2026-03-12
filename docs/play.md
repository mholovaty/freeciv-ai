# Tutorial — Running a Trained Agent Against a Live Server

This tutorial covers `freeciv_ai/torch/play.py`: how to connect a trained checkpoint to a running Freeciv server and watch it play, including multi-agent setups where several AI instances compete against each other.

---

## 1. Overview

`play.py` is a standalone script that:

1. Connects to an **already-running** Freeciv server as a named player.
2. Waits passively for the game to start (the operator sends `/start`).
3. On each turn: builds the observation, runs the policy network, issues moves, ends the turn.
4. Logs every unit action and a per-turn tile-discovery summary.
5. Exits when the game ends (or `--max-turns` is reached).

The script **never starts or stops the server**. Server lifecycle is managed by the operator. This separation makes it composable — you can connect any number of AI instances plus human observers to the same server.

---

## 2. Prerequisites

- A trained checkpoint, e.g. `checkpoints/final.pt` (produced by `train.py`).
- A running `freeciv-server` accepting connections on a known port.
- Optionally: a Freeciv GUI client connected in observer mode to watch.

---

## 3. Single-Agent Quickstart

Start a server manually (or use an existing one), then:

```bash
cd python
python -m freeciv_ai.torch.play \
    --checkpoint checkpoints/final.pt \
    --host localhost \
    --port 5600 \
    --username ai-1
```

The script connects and prints:

```
Connected, state=ClientState.PREPARING
Waiting for game to start...
```

From the server console (or a client with hack level), start the game:

```
/start
```

The agent begins playing immediately. The terminal shows one line per unit action and a summary per turn:

```
  turn   1  unit 42 @ (10,8)  → move NE → (11,7)
  turn   1  unit 43 @ (12,9)  → move N → (12,8)
turn   1  known=47  newly_revealed=+12
  turn   2  unit 42 @ (11,7)  → move E → (12,7)
  ...
=== Episode 1 done after 20 turns, 183 tiles known ===
```

### Auto-start mode

If you are running a local server and want the script to send `/start` itself (no operator needed):

```bash
python -m freeciv_ai.torch.play \
    --checkpoint checkpoints/final.pt \
    --auto-start
```

This requires hack level, which is granted automatically on localhost. It is convenient for automated single-player testing but not suitable for multi-agent games where each player connects at a different time.

---

## 4. Slow Replay for Observation

Use `--delay` to insert a pause after all unit moves are issued but before `end_turn()` is sent. This gives a human observer time to see the moves in the GUI before the turn advances.

```bash
python -m freeciv_ai.torch.play \
    --checkpoint checkpoints/final.pt \
    --delay 2.0
```

Recommended values:

| `--delay` | Use case |
|-----------|----------|
| `0` (default) | Automated runs, no observer |
| `0.5` | Fast observer following along |
| `1.5–2.0` | Comfortable real-time observation |
| `5.0+` | Detailed step-by-step review |

---

## 5. Multi-Agent Setup

This is the main motivation for the passive-connect design. Each AI instance connects as a separate named player; the operator starts the game once all players are in.

### Example: two AI players

**Terminal 1 — Agent A (checkpoint from episode 100):**
```bash
python -m freeciv_ai.torch.play \
    --checkpoint checkpoints/ep000100.pt \
    --host localhost --port 5600 \
    --username agent-a \
    --delay 1.0
```

**Terminal 2 — Agent B (final checkpoint):**
```bash
python -m freeciv_ai.torch.play \
    --checkpoint checkpoints/final.pt \
    --host localhost --port 5600 \
    --username agent-b \
    --delay 1.0
```

**Terminal 3 — Observer GUI client:**
Connect a standard Freeciv client to `localhost:5600` in observer mode.

**Server console — start when both agents are connected:**
```
/list          # verify both players appear
/start
```

Both agents play simultaneously. Each handles only its own units (those returned by `get_units()` for its player slot). The server enforces turn synchronisation — a turn advances when all players have ended their turn.

### Comparing checkpoints

This setup is useful for evaluating whether a newer checkpoint is better than an older one by running them against each other on the same map.

---

## 6. Multi-Episode Runs

Use `--episodes N` to play N games back-to-back without restarting the script. After each game ends the script waits for the next game to start.

```bash
python -m freeciv_ai.torch.play \
    --checkpoint checkpoints/final.pt \
    --episodes 5 \
    --delay 1.0
```

After each game the terminal prints:

```
=== Episode 2 ended. Waiting for operator to start the next game... ===
```

The operator then resets and restarts from the server console:

```
/endgame
/start
```

With `--auto-start` the script issues `/endgame` and `/start` itself between episodes — useful for unattended single-player evaluation runs.

---

## 7. CLI Reference

| Flag | Default | Description |
|------|---------|-------------|
| `--checkpoint` | *(required)* | Path to `.pt` checkpoint file |
| `--host` | `localhost` | Server hostname |
| `--port` | `5600` | Server port |
| `--username` | `rl-agent` | Player name shown in the game |
| `--max-units` | `16` | Must match the value used during training |
| `--max-turns` | `500` | Safety cap; normally the server ends the game first |
| `--delay` | `0.0` | Seconds to pause before `end_turn()` each turn |
| `--episodes` | `1` | Games to play back-to-back |
| `--auto-start` | off | Send `/start` (and `/endgame` between episodes) automatically |
| `--log-level` | `INFO` | Python log level (`DEBUG` for verbose output) |

---

## 8. Log Output Explained

```
  turn   5  unit 42 @ (11,7)  → move NE → (12,6)    # unit moved successfully
  turn   5  unit 43 @ (9,10)  → move N blocked        # target tile invalid or occupied
  turn   5  unit 44 @ (8,8)   → skip                  # policy chose action 0
turn   5  known=183  newly_revealed=+7                 # turn summary
```

- **`known`**: total tiles ever seen (cumulative, not just visible this turn).
- **`newly_revealed`**: tiles seen for the first time this turn — the primary exploration metric.
- **`blocked`**: the policy chose a direction but `can_do_action` rejected it (wall, enemy, out of moves). The unit does nothing; this is normal behaviour.

---

## Next Steps

- **Tutorial 04** (planned): Add a CNN over the map instead of a flat MLP for spatial reasoning.
