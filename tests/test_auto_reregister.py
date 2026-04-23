"""Transport-layer auto re-register on server-side eviction.

Simulates the exact production failure mode: client registers, then
the server evicts the cid (heartbeat_dead sweeper does this after
45 s of silence). The NEXT tool call from the client used to get
back ``{ok: False, error.code: "not_registered"}`` and the adapter
treated it as a terminal match failure.

With the 2026-04-23 transport fix, the client caches the registration
args and transparently re-registers with the same cid when it sees
NOT_REGISTERED, then retries the original call. From the caller's
perspective the hiccup is invisible.
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


class _ServerThread:
    def __init__(self, app_factory, port):
        self._port = port
        self._server: uvicorn.Server | None = None
        self._thread: threading.Thread | None = None
        self._app_factory = app_factory

    def start(self) -> None:
        cfg = uvicorn.Config(
            app=self._app_factory(),
            host="127.0.0.1", port=self._port, log_level="warning",
        )
        self._server = uvicorn.Server(cfg)
        self._thread = threading.Thread(target=self._server.run, daemon=True)
        self._thread.start()
        deadline = time.time() + 10.0
        while time.time() < deadline:
            if self._server.started:
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
    starlette_app = mcp.streamable_http_app()
    t = _ServerThread(lambda: starlette_app, port=port)
    t.start()
    try:
        yield (f"http://127.0.0.1:{port}/mcp/", app)
    finally:
        t.stop()


def test_auto_reregister_on_not_registered(server) -> None:
    """Server evicts the cid mid-session → next game-tool call triggers
    auto-reregister so the server knows the cid again.

    The specific tool call that TRIPPED NOT_REGISTERED will still fail
    (get_state only works from IN_GAME; after auto-reregister we're
    back in IN_LOBBY, so it'll fail with a different code). The
    important invariant is that the cid is reattached — future lobby
    / game activity can proceed instead of silently piling up
    NOT_REGISTERED forever.
    """
    url, app = server

    async def go() -> dict:
        async with ServerClient.connect(url) as client:
            r = await client.call(
                "set_player_metadata",
                display_name="ghost", kind="ai",
                provider="anthropic", model="claude-haiku-4-5",
            )
            assert r["ok"] is True
            cid = client.connection_id
            assert app.get_connection(cid) is not None

            # Simulate heartbeat_dead eviction — the exact thing the
            # server's sweeper does after 45 s of no heartbeat.
            app.drop_connection(cid)
            assert app.get_connection(cid) is None

            # Any game-tool call would have returned NOT_REGISTERED
            # and stayed there forever. With auto-recovery the
            # transport transparently re-invokes set_player_metadata
            # with the same cid, then retries the original call.
            # The retry returns a DIFFERENT error (tool_not_available_
            # in_state — we're IN_LOBBY now, not IN_GAME) but the cid
            # IS re-registered.
            r2 = await client.call("get_state")
            # Regardless of the retry's outcome: server must know the
            # cid again.
            assert app.get_connection(cid) is not None, (
                f"auto-reregister failed — server still doesn't know "
                f"cid={cid}. Response was {r2}"
            )
            # And the error we surface is NOT the NOT_REGISTERED the
            # server would have produced on the first attempt — it's
            # the state-mismatch error from the retry.
            code = (r2.get("error") or {}).get("code")
            assert code != "not_registered", (
                f"auto-recovery didn't run; still seeing NOT_REGISTERED: {r2}"
            )

            # Follow-up: we should now be able to use lobby tools
            # cleanly since we're IN_LOBBY after the auto-reregister.
            w = await client.call("whoami")
            assert w["ok"] is True
            assert w["player"]["display_name"] == "ghost"
            assert w["state"] == ConnectionState.IN_LOBBY.value

            return {"cid": cid}

    info = asyncio.run(go())
    assert info["cid"]
