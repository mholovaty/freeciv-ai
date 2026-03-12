import freeciv_ai.server as server_mod


class _FakeProc:
    def __init__(self) -> None:
        self.returncode = None
        self.stdout = object()
        self.stdin = None
        self.killed = False

    def kill(self) -> None:
        self.killed = True
        self.returncode = -9


async def test_start_sets_linux_parent_death_hook(monkeypatch):
    proc = _FakeProc()
    captured: dict[str, object] = {}

    async def fake_create_subprocess_exec(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return proc

    async def fake_forward_subprocess(_proc, ready_event, ready_pattern):
        assert _proc is proc
        assert "accepting new client connections on port 12345" == ready_pattern
        ready_event.set()

    monkeypatch.setattr(server_mod.sys, "platform", "linux")
    monkeypatch.setattr(server_mod.asyncio, "create_subprocess_exec", fake_create_subprocess_exec)
    monkeypatch.setattr(server_mod, "forward_subprocess", fake_forward_subprocess)

    server = server_mod.FreecivServer()
    await server.start(port=12345, wait_timeout=0.1)

    assert captured["args"][:2] == ("freeciv-server", "-p")
    assert captured["kwargs"]["preexec_fn"] is server_mod._set_parent_death_signal
    assert server in server_mod._LIVE_SERVERS

    server.force_kill()


def test_cleanup_live_servers_force_kills_registered_server():
    server = server_mod.FreecivServer()
    proc = _FakeProc()
    server._proc = proc
    server_mod._LIVE_SERVERS.add(server)

    server_mod._cleanup_live_servers()

    assert proc.killed
    assert server not in server_mod._LIVE_SERVERS
