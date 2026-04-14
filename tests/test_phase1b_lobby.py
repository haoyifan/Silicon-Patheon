"""Phase 1b integration: full lobby -> auto-start -> in-game flow.

Uses monkey-patched AUTOSTART_DELAY_S to avoid real 10s sleeps in
tests — the countdown logic itself is still exercised end-to-end.
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
def fast_countdown(monkeypatch: pytest.MonkeyPatch) -> None:
    """Shrink the autostart countdown so tests don't wait 10 real seconds."""
    monkeypatch.setattr(
        "silicon_pantheon.server.lobby_tools.AUTOSTART_DELAY_S", 0.2
    )


@pytest.fixture
def server(fast_countdown):
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


def test_list_create_preview_join_ready_autostart(server) -> None:
    url, app = server

    async def go() -> None:
        async with (
            ServerClient.connect(url) as blue,
            ServerClient.connect(url) as red,
        ):
            # Declare both.
            await blue.call("set_player_metadata", display_name="alice", kind="ai")
            await red.call("set_player_metadata", display_name="bob", kind="human")

            # Empty lobby initially.
            r = await blue.call("list_rooms")
            assert r["ok"] is True and r["rooms"] == []

            # Host creates.
            r = await blue.call(
                "create_room",
                scenario="01_tiny_skirmish",
                team_assignment="fixed",
                host_team="blue",
                fog_of_war="none",
            )
            assert r["ok"] is True
            room_id = r["room_id"]

            # Red sees it in the list; preview returns the scenario.
            r = await red.call("list_rooms")
            assert any(rm["room_id"] == room_id for rm in r["rooms"])

            r = await red.call("preview_room", room_id=room_id)
            assert r["ok"] is True
            prev = r["room"]["scenario_preview"]
            assert prev["width"] > 0 and prev["height"] > 0
            assert isinstance(prev["units"], list) and len(prev["units"]) > 0

            # Red joins.
            r = await red.call("join_room", room_id=room_id)
            assert r["ok"] is True and r["slot"] == "b"

            # Both ready up. After the second ready, the countdown fires
            # and the (shortened) sleep expires, promoting to IN_GAME.
            await blue.call("set_ready", ready=True)
            await red.call("set_ready", ready=True)

            # Wait a bit beyond the shortened countdown.
            await asyncio.sleep(0.4)

            # Both connections should now be IN_GAME.
            for cid in (blue.connection_id, red.connection_id):
                conn = app.get_connection(cid)
                assert conn is not None
                assert conn.state == ConnectionState.IN_GAME

            # And a game tool works on that session.
            r = await blue.call("get_state")
            assert r["ok"] is True
            assert r["result"]["turn"] == 1

    asyncio.run(go())


def test_unready_cancels_countdown(server) -> None:
    url, app = server

    async def go() -> None:
        async with (
            ServerClient.connect(url) as blue,
            ServerClient.connect(url) as red,
        ):
            await blue.call("set_player_metadata", display_name="alice", kind="ai")
            await red.call("set_player_metadata", display_name="bob", kind="ai")
            r = await blue.call(
                "create_room", scenario="01_tiny_skirmish", fog_of_war="none"
            )
            room_id = r["room_id"]
            await red.call("join_room", room_id=room_id)

            # Start countdown, then immediately unready.
            await blue.call("set_ready", ready=True)
            await red.call("set_ready", ready=True)
            await asyncio.sleep(0.05)
            await red.call("set_ready", ready=False)

            # Wait long enough that the original countdown would have
            # finished; game must not have started.
            await asyncio.sleep(0.4)

            room = app.rooms.get(room_id)
            assert room is not None
            assert room.status.value != "in_game"
            for cid in (blue.connection_id, red.connection_id):
                conn = app.get_connection(cid)
                assert conn is not None
                assert conn.state == ConnectionState.IN_ROOM

    asyncio.run(go())


def test_leave_room_returns_to_lobby(server) -> None:
    url, app = server

    async def go() -> None:
        async with ServerClient.connect(url) as blue:
            await blue.call("set_player_metadata", display_name="alice", kind="ai")
            r = await blue.call(
                "create_room", scenario="01_tiny_skirmish", fog_of_war="none"
            )
            room_id = r["room_id"]
            r = await blue.call("leave_room")
            assert r["ok"] is True
            conn = app.get_connection(blue.connection_id)
            assert conn is not None
            assert conn.state == ConnectionState.IN_LOBBY
            # Empty room was removed.
            assert app.rooms.get(room_id) is None

    asyncio.run(go())
