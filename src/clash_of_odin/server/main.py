"""MCP stdio server for Clash of Odin.

Wraps the in-process tool layer (`server.tools`) for remote clients.

This entrypoint is primarily for Phase 8 (remote agents) and for manual poking.
The MVP match flow (`match.run_match`) calls `server.tools.call_tool` directly
in-process and does not go through MCP.

Session identity: MCP stdio is one-client-per-process, so each server instance
binds to ONE team. Pass `--team blue|red --game <scenario>` at startup. The
match orchestrator (Phase 8) will spawn one server instance per player and
keep them in sync — or switch to HTTP/SSE transport for true multi-client.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from .engine.scenarios import load_scenario
from .engine.state import Team
from .session import new_session
from .tools import TOOL_REGISTRY, ToolError, call_tool


def build_server(team: Team, game: str, replay_path: Path | None = None) -> FastMCP:
    state = load_scenario(game)
    session = new_session(state, replay_path=replay_path)
    mcp = FastMCP(name=f"clash-of-odin-{team.value}")

    # Register each tool in the registry.
    for tool_name, spec in TOOL_REGISTRY.items():
        _register_tool(mcp, tool_name, spec, session, team)

    return mcp


def _register_tool(mcp: FastMCP, name: str, spec: dict, session, viewer: Team) -> None:
    description = spec["description"]

    def _handler(**kwargs) -> str:
        try:
            result = call_tool(session, viewer, name, kwargs)
        except ToolError as e:
            return json.dumps({"error": str(e)})
        return json.dumps(result)

    # FastMCP requires a proper function signature; use a thin wrapper.
    # We pass args through kwargs to keep it generic.
    mcp.add_tool(_handler, name=name, description=description)


def main() -> None:
    p = argparse.ArgumentParser(description="Clash of Odin MCP server")
    p.add_argument("--team", choices=["blue", "red"], required=True)
    p.add_argument("--game", default="01_tiny_skirmish", help="scenario folder name")
    p.add_argument("--replay", type=Path, default=None)
    args = p.parse_args()

    server = build_server(Team(args.team), args.game, args.replay)
    # FastMCP.run() uses stdio by default.
    try:
        server.run()
    except KeyboardInterrupt:
        sys.exit(0)


if __name__ == "__main__":
    main()
