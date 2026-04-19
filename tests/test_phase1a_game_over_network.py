"""Phase 1a.13 — two clients exercise game tools over MCP+SSE.

Proves the end-to-end path:
  client A  --MCP+SSE-->  server  --in-process-->  engine

without needing a full random-bot orchestrator. The flow is
scripted: connect both, host + join, each side takes one concrete
action, verify state mutations land authoritatively on the server
and the opposing client sees them on its next get_state call.
"""

from __future__ import annotations

import asyncio
import socket
import threading
import time

import pytest
import uvicorn

from silicon_pantheon.client.transport import ServerClient
from silicon_pantheon.server.app import App, build_mcp_server
from silicon_pantheon.shared.protocol import ConnectionState


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def server():
    app = App()
    mcp = build_mcp_server(app)
    port = _free_port()
    starlette_app = mcp.streamable_http_app()
    config = uvicorn.Config(
        app=starlette_app, host="127.0.0.1", port=port, log_level="warning"
    )
    srv = uvicorn.Server(config)
    thread = threading.Thread(target=srv.run, daemon=True)
    thread.start()
    deadline = time.time() + 10.0
    while time.time() < deadline and not srv.started:
        time.sleep(0.05)
    if not srv.started:
        raise RuntimeError("uvicorn failed to start")
    try:
        yield f"http://127.0.0.1:{port}/mcp/", app
    finally:
        srv.should_exit = True
        thread.join(timeout=5.0)


def test_two_clients_host_join_and_act(server) -> None:
    url, app = server

    async def go() -> None:
        async with (
            ServerClient.connect(url) as blue,
            ServerClient.connect(url) as red,
        ):
            # 1. Both declare themselves.
            await blue.call("set_player_metadata", display_name="alice", kind="ai")
            await red.call("set_player_metadata", display_name="bob", kind="ai")

            # 2. Blue hosts; Red joins → game starts.
            r = await blue.call("create_dev_game", scenario="01_tiny_skirmish")
            assert r["ok"] is True and r["slot"] == "a"
            r = await red.call("join_dev_game")
            assert r["ok"] is True and r["slot"] == "b"

            # 3. Server should now have both connections IN_GAME.
            for cid in (blue.connection_id, red.connection_id):
                conn = app.get_connection(cid)
                assert conn is not None
                assert conn.state == ConnectionState.IN_GAME

            # 4. Blue reads state, confirms it's blue's turn on turn 1.
            r = await blue.call("get_state")
            assert r["ok"] is True
            gs = r["result"]
            assert gs["turn"] == 1
            assert gs["active_player"] == "blue"

            # 5. Red calling a turn-gated tool in blue's turn should error.
            #    (`move` requires active_player == viewer.)
            r = await red.call("end_turn")
            assert r["ok"] is False  # not your turn

            # 6. Blue ends turn (no moves — still valid if no mid-action units).
            r = await blue.call("end_turn")
            assert r["ok"] is True

            # 7. After end_turn, active_player flips to red and red can act.
            r = await red.call("get_state")
            assert r["ok"] is True
            assert r["result"]["active_player"] == "red"
            r = await red.call("end_turn")
            assert r["ok"] is True

            # 8. One full round completed — turn counter bumped to 2.
            r = await blue.call("get_state")
            assert r["ok"] is True
            assert r["result"]["turn"] == 2

    asyncio.run(go())


def test_game_tool_rejects_in_lobby_connection(server) -> None:
    url, _app = server

    async def go() -> None:
        async with ServerClient.connect(url) as c:
            # Declared → IN_LOBBY. Game tool should refuse on state.
            await c.call("set_player_metadata", display_name="alice", kind="ai")
            r = await c.call("get_state")
            assert r["ok"] is False
            assert r["error"]["code"] == "tool_not_available_in_state"

    asyncio.run(go())


def test_game_tool_rejects_unknown_connection(server) -> None:
    url, _app = server

    async def go() -> None:
        async with ServerClient.connect(url) as c:
            # Fresh connection, never called set_player_metadata.
            # `_dispatch` sees an unknown connection_id and returns
            # NOT_REGISTERED — only set_player_metadata creates connections.
            r = await c.call("get_state")
            assert r["ok"] is False
            assert r["error"]["code"] == "not_registered"

    asyncio.run(go())
