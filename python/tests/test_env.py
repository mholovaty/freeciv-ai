"""
Smoke tests for FreecivEnv.

Verifies that:
- reset() returns a correctly shaped float32 observation
- step() returns (obs, float reward, bool done, dict info)
- reward shape and types are correct

All tests share one FreecivEnv via the module-scoped ``env`` fixture.
freeciv_ai_connect() (which runs client_main()) can only be called once per
process; subsequent episodes use the safe reconnect() path via reset().
"""

import logging

import pytest
import pytest_asyncio
import torch

from freeciv_ai import setup_logging
from freeciv_ai._logging import start_log_tasks, stop_log_tasks

from freeciv_ai.torch.env import FreecivEnv
from conftest import timeout, get_free_port

_MAX_TURNS = 5


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def env():
    """Single FreecivEnv shared across all tests in this module."""
    setup_logging(level=logging.WARNING)
    await start_log_tasks()
    port = get_free_port()
    e = FreecivEnv(max_turns=_MAX_TURNS, port=port)
    yield e
    await e.close()
    await stop_log_tasks()


@pytest.mark.asyncio(loop_scope="module")
@timeout(120)
async def test_env_reset_returns_tensor(env):
    """reset() should return a 1-D float32 tensor."""
    obs = await env.reset()
    assert isinstance(obs, torch.Tensor), "obs must be a Tensor"
    assert obs.dtype == torch.float32
    assert obs.dim() == 1
    assert obs.shape[0] == env.obs_size


@pytest.mark.asyncio(loop_scope="module")
@timeout(120)
async def test_env_step_types(env):
    """step() should return (Tensor, float, bool, dict)."""
    obs = await env.reset()
    n_units = len(env.last_units) or 1
    actions = [0] * n_units  # all-skip

    next_obs, reward, done, info = await env.step(actions)

    assert isinstance(next_obs, torch.Tensor)
    assert next_obs.dtype == torch.float32
    assert next_obs.shape == obs.shape
    assert isinstance(reward, float)
    assert isinstance(done, bool)
    assert isinstance(info, dict)
    assert "turn" in info
    assert "known_tiles" in info


@pytest.mark.asyncio(loop_scope="module")
@timeout(180)
async def test_env_episode_ends_at_max_turns(env):
    """Episode should terminate at max_turns."""
    await env.reset()
    done = False
    steps = 0
    while not done:
        n_units = len(env.last_units) or 1
        _, _, done, info = await env.step([0] * n_units)
        steps += 1
        assert steps <= _MAX_TURNS + 1, "episode ran longer than max_turns"
    assert steps == _MAX_TURNS
