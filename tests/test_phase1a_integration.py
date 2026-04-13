"""Phase 1a integration: a real MCP+SSE connection between client and server.

Spins up the server's Starlette app under uvicorn in a background
thread on an ephemeral port, then drives it through the real
streamable-HTTP client wrapper. Proves the transport, tool dispatch,
and per-connection state machinery work end-to-end.
"""

from __future__ import annotations

import asyncio
import socket
import threading
import time

import pytest
import uvicorn

from clash_of_odin.client.transport import ServerClient
from clash_of_odin.server.app import App, build_mcp_server
from clash_of_odin.shared.protocol import ConnectionState


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class _ServerThread:
    """Run a uvicorn server in a background thread and signal readiness."""

    def __init__(self, app_factory, port: int):
        self._port = port
        self._ready = threading.Event()
        self._server: uvicorn.Server | None = None
        self._thread: threading.Thread | None = None
        self._app_factory = app_factory

    def start(self) -> None:
        config = uvicorn.Config(
            app=self._app_factory(),
            host="127.0.0.1",
            port=self._port,
            log_level="warning",
        )
        self._server = uvicorn.Server(config)
        # uvicorn doesn't expose a simple "wait for ready" hook, so poll.
        self._thread = threading.Thread(target=self._server.run, daemon=True)
        self._thread.start()
        deadline = time.time() + 10.0
        while time.time() < deadline:
            if self._server.started:
                self._ready.set()
                return
            time.sleep(0.05)
        raise RuntimeError("uvicorn failed to start in 10s")

    def stop(self) -> None:
        if self._server is not None:
            self._server.should_exit = True
        if self._thread is not None:
            self._thread.join(timeout=5.0)


@pytest.fixture
def server():
    app = App()
    mcp = build_mcp_server(app)
    port = _free_port()
    # FastMCP's streamable_http_app provides the Starlette app we mount.
    starlette_app = mcp.streamable_http_app()
    server_thread = _ServerThread(lambda: starlette_app, port=port)
    server_thread.start()
    try:
        yield (f"http://127.0.0.1:{port}/mcp/", app)
    finally:
        server_thread.stop()


def test_end_to_end_metadata_roundtrip(server) -> None:
    url, app = server

    async def go() -> dict:
        async with ServerClient.connect(url) as client:
            r1 = await client.call("whoami")
            assert r1["state"] == ConnectionState.ANONYMOUS.value
            r2 = await client.call(
                "set_player_metadata",
                display_name="alice",
                kind="ai",
                provider="anthropic",
                model="claude-haiku-4-5",
            )
            assert r2["ok"] is True
            assert r2["state"] == ConnectionState.IN_LOBBY.value
            r3 = await client.call("heartbeat")
            assert r3["ok"] is True
            r4 = await client.call("whoami")
            assert r4["player"]["display_name"] == "alice"
            return {"connection_id": client.connection_id}

    info = asyncio.run(go())
    # The server side should have recorded this connection.
    conn = app.get_connection(info["connection_id"])
    assert conn is not None
    assert conn.player is not None
    assert conn.player.display_name == "alice"
    assert conn.state == ConnectionState.IN_LOBBY


def test_two_clients_isolated(server) -> None:
    url, app = server

    async def go() -> tuple[str, str]:
        async with ServerClient.connect(url) as a, ServerClient.connect(url) as b:
            await a.call("set_player_metadata", display_name="alice", kind="ai")
            await b.call("set_player_metadata", display_name="bob", kind="human")
            wa = await a.call("whoami")
            wb = await b.call("whoami")
            assert wa["player"]["display_name"] == "alice"
            assert wb["player"]["display_name"] == "bob"
            return a.connection_id, b.connection_id

    cid_a, cid_b = asyncio.run(go())
    assert cid_a != cid_b
    ca = app.get_connection(cid_a)
    cb = app.get_connection(cid_b)
    assert ca is not None and ca.player is not None
    assert cb is not None and cb.player is not None
    assert ca.player.display_name == "alice"
    assert cb.player.display_name == "bob"
