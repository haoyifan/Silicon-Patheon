"""Tests for the client/server protocol-version handshake."""

from __future__ import annotations

import asyncio
import json

from silicon_pantheon.server.app import App, build_mcp_server
from silicon_pantheon.shared.protocol import (
    MINIMUM_CLIENT_PROTOCOL_VERSION,
    PROTOCOL_VERSION,
    ErrorCode,
)


def _call(mcp, name: str, **kwargs) -> dict:
    blocks = asyncio.run(mcp.call_tool(name, kwargs))
    for block in blocks:
        text = getattr(block, "text", None)
        if text is not None:
            return json.loads(text)
    raise RuntimeError(f"tool {name} returned no text block: {blocks!r}")


def test_server_reports_protocol_version_in_response() -> None:
    mcp = build_mcp_server(App())
    r = _call(
        mcp,
        "set_player_metadata",
        connection_id="c1",
        display_name="alice",
        kind="ai",
    )
    assert r["ok"] is True
    assert r["server_protocol_version"] == PROTOCOL_VERSION
    assert r["minimum_client_protocol_version"] == MINIMUM_CLIENT_PROTOCOL_VERSION


def test_client_with_matching_version_accepted() -> None:
    mcp = build_mcp_server(App())
    r = _call(
        mcp,
        "set_player_metadata",
        connection_id="c1",
        display_name="alice",
        kind="ai",
        client_protocol_version=PROTOCOL_VERSION,
    )
    assert r["ok"] is True


def test_client_below_minimum_refused() -> None:
    """Clients whose protocol version is below the server's minimum
    supported version get CLIENT_TOO_OLD and are expected to upgrade."""
    import silicon_pantheon.server.app as srv_app
    original_min = srv_app.MINIMUM_CLIENT_PROTOCOL_VERSION
    srv_app.MINIMUM_CLIENT_PROTOCOL_VERSION = 5
    try:
        mcp = build_mcp_server(App())
        r = _call(
            mcp,
            "set_player_metadata",
            connection_id="c1",
            display_name="alice",
            kind="ai",
            client_protocol_version=3,
        )
        assert r["ok"] is False
        assert r["error"]["code"] == ErrorCode.CLIENT_TOO_OLD.value
        data = r["error"].get("data") or {}
        assert data.get("minimum_client_protocol_version") == 5
        assert data.get("client_protocol_version") == 3
        assert "upgrade_command" in data
    finally:
        srv_app.MINIMUM_CLIENT_PROTOCOL_VERSION = original_min


def test_client_above_server_version_accepted() -> None:
    """Newer clients talking to older servers are accepted (the
    server stays operational; the client is responsible for not
    using features the server doesn't advertise)."""
    mcp = build_mcp_server(App())
    r = _call(
        mcp,
        "set_player_metadata",
        connection_id="c1",
        display_name="alice",
        kind="ai",
        client_protocol_version=PROTOCOL_VERSION + 5,
    )
    assert r["ok"] is True


def test_client_omitting_version_treated_as_v1() -> None:
    """A client that doesn't send client_protocol_version is treated
    as v1 (the pre-handshake-aware behavior). At MIN=1 that's
    accepted; when MIN > 1 it's rejected — covered by the next test."""
    mcp = build_mcp_server(App())
    r = _call(
        mcp,
        "set_player_metadata",
        connection_id="c1",
        display_name="alice",
        kind="ai",
    )
    assert r["ok"] is True


def test_client_omitting_version_rejected_once_minimum_exceeds_v1() -> None:
    """Regression guard for Phase 4 of the breaking-change rollout:
    once MINIMUM_CLIENT_PROTOCOL_VERSION is raised above 1, a client
    that doesn't send client_protocol_version at all (pre-handshake-
    aware) falls to the effective v1 baseline and gets CLIENT_TOO_OLD,
    not a silent pass. See docs/VERSIONING.md."""
    import silicon_pantheon.server.app as srv_app
    original_min = srv_app.MINIMUM_CLIENT_PROTOCOL_VERSION
    srv_app.MINIMUM_CLIENT_PROTOCOL_VERSION = 2
    try:
        mcp = build_mcp_server(App())
        r = _call(
            mcp,
            "set_player_metadata",
            connection_id="c1",
            display_name="alice",
            kind="ai",
            # client_protocol_version deliberately omitted
        )
        assert r["ok"] is False
        assert r["error"]["code"] == ErrorCode.CLIENT_TOO_OLD.value
        assert r["error"]["data"]["client_protocol_version"] == 1
    finally:
        srv_app.MINIMUM_CLIENT_PROTOCOL_VERSION = original_min


def test_client_sending_stringified_version_is_parsed() -> None:
    """Legacy callers that sent client_protocol_version as a
    stringified number ('1') should still be interpreted correctly
    rather than silently falling back to v1-via-parse-failure."""
    mcp = build_mcp_server(App())
    r = _call(
        mcp,
        "set_player_metadata",
        connection_id="c1",
        display_name="alice",
        kind="ai",
        client_protocol_version="1",
    )
    assert r["ok"] is True


def test_connection_records_client_protocol_version() -> None:
    """The server must retain the client's version on the Connection
    object so later tool handlers can branch their wire shape during
    a compat-shim window."""
    app = App()
    mcp = build_mcp_server(app)
    r = _call(
        mcp,
        "set_player_metadata",
        connection_id="c1",
        display_name="alice",
        kind="ai",
        client_protocol_version=PROTOCOL_VERSION,
    )
    assert r["ok"] is True
    conn = app.get_connection("c1")
    assert conn is not None
    assert conn.client_protocol_version == PROTOCOL_VERSION
