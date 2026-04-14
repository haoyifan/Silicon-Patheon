"""H.1: describe_scenario returns the full scenario bundle.

Direct-invoke test: we build the server MCP instance and call the
tool via its tool manager so we don't need uvicorn + an HTTP loop.
"""

from __future__ import annotations

import asyncio

import pytest

from clash_of_odin.server.app import App, build_mcp_server
from clash_of_odin.shared.protocol import ConnectionState


@pytest.fixture
def authed_app():
    """An App with one authenticated connection ready to call lobby tools."""
    app = App()
    mcp = build_mcp_server(app)
    # Register a live connection through the public path. set_player_metadata
    # promotes ANONYMOUS → IN_LOBBY.
    conn = app.ensure_connection("c_test_1")
    conn.state = ConnectionState.IN_LOBBY
    return mcp, app, conn.id


def _call(mcp, tool_name: str, **kwargs) -> dict:
    """Invoke a FastMCP-registered tool directly and return its JSON payload."""
    result = asyncio.run(mcp._tool_manager.call_tool(tool_name, kwargs))
    if isinstance(result, dict):
        return result
    sc = getattr(result, "structured_content", None)
    if sc is not None:
        return sc
    import json
    tc = getattr(result, "content", None) or []
    if tc and getattr(tc[0], "text", None):
        return json.loads(tc[0].text)
    raise AssertionError(f"unexpected tool result shape: {result!r}")


def test_describe_scenario_returns_full_bundle(authed_app) -> None:
    mcp, app, cid = authed_app
    out = _call(mcp, "describe_scenario", connection_id=cid, name="01_tiny_skirmish")
    assert out.get("ok") is True
    data = out
    assert "unit_classes" in data
    # Built-in classes come through even when scenario didn't override.
    assert "knight" in data["unit_classes"]
    assert "archer" in data["unit_classes"]
    assert "terrain_types" in data
    # The 4 default terrain names are always present.
    for name in ("plain", "forest", "mountain", "fort"):
        assert name in data["terrain_types"]
    assert "win_conditions" in data  # even if empty list
    assert "board" in data
    assert data["board"]["width"] == 6


def test_describe_scenario_includes_jttw_custom_classes(authed_app) -> None:
    mcp, app, cid = authed_app
    out = _call(mcp, "describe_scenario", connection_id=cid, name="journey_to_the_west")
    assert out.get("ok") is True
    assert "tang_monk" in out["unit_classes"]
    assert "sun_wukong" in out["unit_classes"]
    assert "river" in out["terrain_types"]
    assert any(wc.get("type") == "protect_unit" for wc in out["win_conditions"])
    assert out["narrative"]["title"] == "Journey to the West"


def test_describe_scenario_unknown_name_errors(authed_app) -> None:
    mcp, app, cid = authed_app
    out = _call(mcp, "describe_scenario", connection_id=cid, name="does_not_exist")
    assert out.get("ok") is False
    err_msg = out.get("error", {})
    if isinstance(err_msg, dict):
        err_msg = err_msg.get("message", "")
    assert "unknown scenario" in err_msg.lower()
