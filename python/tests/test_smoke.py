"""
Smoke test: start a local server, connect, wait for game to start, exit.

Isolation:
  - uses a free TCP port (no clash with a running server on 5556)
  - disables autosaves so no .sav files are created
  - routes save files to a temporary directory (belt-and-suspenders)
"""

import asyncio
import logging
import tempfile

from freeciv_ai import FreecivClient, ClientState, setup_logging
from freeciv_ai._logging import start_log_tasks, stop_log_tasks

from conftest import timeout, get_free_port

log = logging.getLogger(__name__)


@timeout(30)
async def test_local_game_starts_and_exits():
    """Start a local server, connect, confirm game is running, disconnect."""
    setup_logging(level=logging.INFO)
    await start_log_tasks()

    port = get_free_port()

    try:
        with tempfile.TemporaryDirectory() as savedir:
            with FreecivClient() as client:
                server = await client.start_server(
                    port=port,
                    username="smoke-test",
                    auto_start=True,
                    saves_dir=savedir,
                    extra_cmds=[
                        "/set autosaves 0",          # no periodic saves
                    ],
                )
                try:
                    while not client.in_game:
                        if client.state == ClientState.DISCONNECTED:
                            raise ConnectionError("Disconnected before game started")
                        await asyncio.sleep(0.05)

                    assert client.state == ClientState.RUNNING
                    log.info("Game started — turn %d", client.turn)

                    # Wait for our turn
                    await client.wait_for_turn()
                    log.info("Our turn — listing units")

                    units = client.get_units()
                    for u in units:
                        log.info("  unit %d  %s  @ (%d,%d)  HP %d/%d  moves %d/%d",
                                 u["id"], u["type"], u["x"], u["y"],
                                 u["hp"], u["hp_max"],
                                 u["moves_left"], u["moves_max"])

                    log.info("Ending turn")
                    client.end_turn()

                    log.info("Disconnecting")
                finally:
                    await server.stop()
    finally:
        await stop_log_tasks()
