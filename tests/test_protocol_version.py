"""Tests for the client/server protocol-version handshake."""

from __future__ import annotations

import asyncio
import json

from silicon_pantheon.server.app import App, build_mcp_server
from silicon_pantheon.shared.protocol import PROTOCOL_VERSION, ErrorCode


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


def test_client_with_mismatched_version_refused() -> None:
    mcp = build_mcp_server(App())
    # Older client.
    r = _call(
        mcp,
        "set_player_metadata",
        connection_id="c1",
        display_name="alice",
        kind="ai",
        client_protocol_version=0,
    )
    assert r["ok"] is False
    assert r["error"]["code"] == ErrorCode.VERSION_MISMATCH.value
    assert "v0" in r["error"]["message"]
    # Newer client.
    r = _call(
        mcp,
        "set_player_metadata",
        connection_id="c2",
        display_name="bob",
        kind="ai",
        client_protocol_version=PROTOCOL_VERSION + 1,
    )
    assert r["ok"] is False
    assert r["error"]["code"] == ErrorCode.VERSION_MISMATCH.value


def test_client_omitting_version_still_accepted_at_v1() -> None:
    """Old clients that never learned to send the version keep working
    at v1. Once we bump to v2 this test gets updated to assert refusal."""
    mcp = build_mcp_server(App())
    r = _call(
        mcp,
        "set_player_metadata",
        connection_id="c1",
        display_name="alice",
        kind="ai",
    )
    assert r["ok"] is True
