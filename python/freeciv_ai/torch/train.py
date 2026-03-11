"""
REINFORCE training loop for the Freeciv exploration task.

Usage::

    python -m freeciv_ai.torch.train --episodes 200 --turns 20

Algorithm
---------
Vanilla policy gradient (REINFORCE) with a learned value baseline:

    advantage_t = G_t - V(s_t)
    policy_loss = -mean(log_π(a_t|s_t) * advantage_t)
    value_loss  = mean((G_t - V(s_t))^2)
    loss        = policy_loss + value_coef * value_loss - entropy_coef * entropy
"""

import argparse
import asyncio
import logging
from pathlib import Path

import torch
import torch.optim as optim

from freeciv_ai import setup_logging
from freeciv_ai._logging import start_log_tasks, stop_log_tasks

from .env import FreecivEnv
from .model import ExplorerPolicy

log = logging.getLogger(__name__)


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Train ExplorerPolicy with REINFORCE")
    p.add_argument("--episodes", type=int, default=200, help="number of training episodes")
    p.add_argument("--turns", type=int, default=20, help="max turns per episode")
    p.add_argument("--lr", type=float, default=3e-4, help="Adam learning rate")
    p.add_argument("--gamma", type=float, default=0.99, help="discount factor")
    p.add_argument("--value-coef", type=float, default=0.5, help="value loss coefficient")
    p.add_argument("--entropy-coef", type=float, default=0.01, help="entropy bonus coefficient")
    p.add_argument("--hidden", type=int, default=256, help="hidden layer size")
    p.add_argument("--max-units", type=int, default=16, help="max units tracked")
    p.add_argument("--port", type=int, default=5600, help="server port")
    p.add_argument("--save-every", type=int, default=50, help="save checkpoint every N episodes")
    p.add_argument("--checkpoint", type=Path, default=Path("checkpoints"), help="checkpoint directory")
    p.add_argument("--resume", type=Path, default=None, help="resume from checkpoint file")
    p.add_argument("--log-level", default="INFO")
    return p.parse_args()


def _discounted_returns(rewards: list[float], gamma: float) -> torch.Tensor:
    """Compute discounted return G_t for each timestep."""
    returns = []
    g = 0.0
    for r in reversed(rewards):
        g = r + gamma * g
        returns.insert(0, g)
    t = torch.tensor(returns, dtype=torch.float32)
    # normalise for stable gradients
    if t.std() > 1e-8:
        t = (t - t.mean()) / (t.std() + 1e-8)
    return t


async def _run_episode(
    env: FreecivEnv,
    policy: ExplorerPolicy,
) -> tuple[list[torch.Tensor], list[torch.Tensor], list[list[int]], list[float]]:
    """
    Collect one full episode.

    Returns
    -------
    observations: list of obs tensors, length T
    masks:        list of action_mask tensors (max_units, 9), length T
    actions:      list of action lists (one per step), length T
    rewards:      list of floats, length T
    """
    obs = await env.reset()
    observations, masks, actions_taken, rewards = [], [], [], []
    done = False

    while not done:
        n_units = len(env.last_units)
        mask = env.last_mask
        acts, _ = policy.select_actions(obs, n_units or 1, mask)
        next_obs, reward, done, info = await env.step(acts)
        observations.append(obs)
        masks.append(mask)
        actions_taken.append(acts)
        rewards.append(reward)
        obs = next_obs
        log.debug("turn %d  reward %.2f  known %d", info["turn"], reward, info["known_tiles"])

    return observations, masks, actions_taken, rewards


def _update(
    policy: ExplorerPolicy,
    optimizer: optim.Optimizer,
    observations: list[torch.Tensor],
    masks: list[torch.Tensor],
    actions_taken: list[list[int]],
    rewards: list[float],
    gamma: float,
    value_coef: float,
    entropy_coef: float,
    max_units: int,
) -> dict[str, float]:
    """Compute REINFORCE + baseline loss and take one gradient step."""
    returns = _discounted_returns(rewards, gamma)  # (T,)
    T = len(observations)

    obs_batch = torch.stack(observations)           # (T, obs_size)
    masks_batch = torch.stack(masks)                # (T, max_units, 9)
    # pad each step's actions to max_units
    acts_padded = torch.zeros(T, max_units, dtype=torch.long)
    for t, acts in enumerate(actions_taken):
        for i, a in enumerate(acts[:max_units]):
            acts_padded[t, i] = a

    n_units = max(len(a) for a in actions_taken) or 1
    log_probs, values, entropy = policy.evaluate_actions(
        obs_batch, acts_padded[:, :n_units], n_units, masks_batch
    )

    advantages = returns - values.detach()
    policy_loss = -(log_probs * advantages).mean()
    value_loss = (returns - values).pow(2).mean()
    loss = policy_loss + value_coef * value_loss - entropy_coef * entropy

    optimizer.zero_grad()
    loss.backward()
    torch.nn.utils.clip_grad_norm_(policy.parameters(), max_norm=0.5)
    optimizer.step()

    return {
        "loss": loss.item(),
        "policy_loss": policy_loss.item(),
        "value_loss": value_loss.item(),
        "entropy": entropy.item(),
        "return": sum(rewards),
    }


async def train(args: argparse.Namespace) -> None:
    setup_logging(level=getattr(logging, args.log_level.upper()))
    await start_log_tasks()

    try:
        await _train_loop(args)
    finally:
        await stop_log_tasks()


async def _train_loop(args: argparse.Namespace) -> None:
    # One persistent env for the entire training session.
    # reset() starts the server on the first call; subsequent calls use /endgame + /start.
    env = FreecivEnv(max_turns=args.turns, port=args.port, max_units=args.max_units)

    # Bootstrap: start server, get obs_size.  Server stays up — no close().
    log.info("Bootstrapping env to get observation size...")
    obs = await env.reset()
    obs_size = obs.shape[0]

    policy = ExplorerPolicy(obs_size=obs_size, max_units=args.max_units, hidden_size=args.hidden)
    optimizer = optim.Adam(policy.parameters(), lr=args.lr)
    start_episode = 0

    if args.resume and args.resume.exists():
        ckpt = torch.load(args.resume, weights_only=True)
        policy.load_state_dict(ckpt["model"])
        optimizer.load_state_dict(ckpt["optimizer"])
        start_episode = ckpt.get("episode", 0)
        log.info("Resumed from %s (episode %d)", args.resume, start_episode)

    args.checkpoint.mkdir(parents=True, exist_ok=True)
    log.info("obs_size=%d  max_units=%d  hidden=%d", obs_size, args.max_units, args.hidden)

    try:
        for ep in range(start_episode, start_episode + args.episodes):
            observations, masks, actions_taken, rewards = [], [], [], []
            try:
                # _run_episode calls env.reset() internally, which ends the
                # previous game (via /endgame) and starts a fresh one.
                observations, masks, actions_taken, rewards = await _run_episode(env, policy)
            except Exception as exc:
                log.warning("ep %4d  failed (%s: %s) — skipping update", ep + 1, type(exc).__name__, exc)

            if not observations:
                continue

            stats = _update(
                policy, optimizer, observations, masks, actions_taken, rewards,
                args.gamma, args.value_coef, args.entropy_coef, args.max_units,
            )
            log.info(
                "ep %4d  return=%.2f  loss=%.4f  π=%.4f  V=%.4f  H=%.4f",
                ep + 1, stats["return"], stats["loss"],
                stats["policy_loss"], stats["value_loss"], stats["entropy"],
            )

            if (ep + 1) % args.save_every == 0:
                path = args.checkpoint / f"ep{ep + 1:06d}.pt"
                torch.save({"episode": ep + 1, "model": policy.state_dict(), "optimizer": optimizer.state_dict()}, path)
                log.info("Saved checkpoint → %s", path)
    finally:
        await env.close()

    # Final checkpoint
    path = args.checkpoint / "final.pt"
    torch.save({"episode": start_episode + args.episodes, "model": policy.state_dict(), "optimizer": optimizer.state_dict()}, path)
    log.info("Training complete. Final model → %s", path)


def main() -> None:
    asyncio.run(train(_parse_args()))


if __name__ == "__main__":
    main()
