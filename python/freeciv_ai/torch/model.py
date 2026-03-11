"""
ExplorerPolicy: shared MLP trunk with policy + value heads.

Input
-----
Flat observation vector produced by ``FreecivEnv`` of size
``map_w * map_h + max_units * 3``.

Output
------
- ``action_logits``: shape ``(n_units, N_ACTIONS)`` — one distribution per unit
- ``value``:         shape ``()``                  — scalar state value for baseline
"""

import torch
import torch.nn as nn
from torch.distributions import Categorical

N_ACTIONS = 9  # 0=skip, 1..8=directions


class ExplorerPolicy(nn.Module):
    """
    MLP actor-critic for the Freeciv exploration task.

    Parameters
    ----------
    obs_size:
        Size of the flat observation vector (``FreecivEnv.obs_size``).
    max_units:
        Maximum number of units the model handles simultaneously.
    hidden_size:
        Width of each hidden layer in the shared trunk.
    """

    def __init__(
        self,
        obs_size: int,
        max_units: int,
        hidden_size: int = 256,
    ) -> None:
        super().__init__()
        self.max_units = max_units

        self.trunk = nn.Sequential(
            nn.Linear(obs_size, hidden_size),
            nn.ReLU(),
            nn.Linear(hidden_size, hidden_size),
            nn.ReLU(),
        )
        self.policy_head = nn.Linear(hidden_size, max_units * N_ACTIONS)
        self.value_head = nn.Linear(hidden_size, 1)

    def forward(
        self, obs: torch.Tensor, n_units: int, action_mask: "torch.Tensor | None" = None
    ) -> tuple[torch.Tensor, torch.Tensor]:
        """
        Parameters
        ----------
        obs:
            Flat observation, shape ``(obs_size,)`` or ``(batch, obs_size)``.
        n_units:
            Number of active units this step (≤ max_units).
        action_mask:
            Optional boolean tensor, shape ``(max_units, 9)`` or
            ``(batch, max_units, 9)``.  ``True`` = action is valid.
            Invalid actions are set to ``-inf`` before softmax so they get
            zero probability.  If ``None``, no masking is applied.

        Returns
        -------
        action_logits:
            Shape ``(..., n_units, N_ACTIONS)``.
        value:
            Shape ``(...)`` scalar(s).
        """
        features = self.trunk(obs)
        logits = self.policy_head(features)
        # reshape to (..., max_units, N_ACTIONS), then trim to n_units
        logits = logits.view(*obs.shape[:-1], self.max_units, N_ACTIONS)
        logits = logits[..., :n_units, :]
        if action_mask is not None:
            # trim mask to n_units along the unit axis and apply
            mask = action_mask[..., :n_units, :]
            logits = logits.masked_fill(~mask, float("-inf"))
        value = self.value_head(features).squeeze(-1)
        return logits, value

    def select_actions(
        self, obs: torch.Tensor, n_units: int, action_mask: "torch.Tensor | None" = None
    ) -> tuple[list[int], torch.Tensor]:
        """
        Sample one action per unit from the current policy.

        Parameters
        ----------
        action_mask:
            Optional ``(max_units, 9)`` bool tensor.  Invalid actions are
            excluded from sampling (probability = 0).

        Returns
        -------
        actions:
            List of ``n_units`` integer action indices.
        log_probs:
            Sum of log-probabilities for all units, shape ``()``.
        """
        with torch.no_grad():
            logits, _ = self.forward(obs, n_units, action_mask)
        dist = Categorical(logits=logits)
        sampled = dist.sample()                          # (n_units,)
        log_probs = dist.log_prob(sampled).sum()         # scalar
        return sampled.tolist(), log_probs

    def evaluate_actions(
        self,
        obs: torch.Tensor,
        actions: torch.Tensor,
        n_units: int,
        action_masks: "torch.Tensor | None" = None,
    ) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """
        Compute log-probs, value, and entropy for a batch of (obs, actions).

        Parameters
        ----------
        obs:
            Shape ``(T, obs_size)``.
        actions:
            Shape ``(T, n_units)`` integer action indices.
        n_units:
            Number of active units.
        action_masks:
            Optional ``(T, max_units, 9)`` bool tensor — one mask per timestep.

        Returns
        -------
        log_probs: ``(T,)`` — sum of per-unit log-probs
        values:    ``(T,)``
        entropy:   scalar mean entropy across steps and units
        """
        logits, values = self.forward(obs, n_units, action_masks)  # (T, n_units, 9), (T,)
        dist = Categorical(logits=logits)
        log_probs = dist.log_prob(actions).sum(-1)       # (T,)
        entropy = dist.entropy().mean()
        return log_probs, values, entropy
