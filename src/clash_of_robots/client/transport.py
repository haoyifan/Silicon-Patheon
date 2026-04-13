"""MCP streamable-HTTP client wrapper.

Wraps the raw mcp SDK client bits into a small async-only API that
matches how our tools look from the caller's perspective: pass a
tool name + kwargs, get back the structured dict the server returned.

All transport errors bubble up as-is so the caller can distinguish
"network said no" from "tool returned {ok: false, error: ...}".
"""

from __future__ import annotations

import json
import secrets
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client


class RemoteToolError(RuntimeError):
    """Raised when a tool call returned no parseable structured body."""


class ServerClient:
    """Connected MCP client. Use via `ServerClient.connect(url)` as an
    async context manager."""

    def __init__(self, session: ClientSession, *, connection_id: str):
        self._session = session
        self.connection_id = connection_id

    @classmethod
    @asynccontextmanager
    async def connect(
        cls,
        url: str,
        *,
        connection_id: str | None = None,
    ) -> AsyncIterator["ServerClient"]:
        """Open an MCP+SSE connection to the server and initialize it.

        Yields a ServerClient ready for tool calls.
        """
        cid = connection_id or secrets.token_hex(8)
        async with streamablehttp_client(url) as (read, write, _get_session_id):
            async with ClientSession(read, write) as session:
                await session.initialize()
                yield cls(session, connection_id=cid)

    async def call(self, tool_name: str, **kwargs: Any) -> dict:
        """Call a server tool, returning the structured response dict.

        The server always returns JSON wrapped in a TextContent block;
        this helper parses that back out. `connection_id` is injected
        automatically so callers can focus on tool-specific args.
        """
        args = {"connection_id": self.connection_id, **kwargs}
        result = await self._session.call_tool(tool_name, args)
        for block in result.content:
            text = getattr(block, "text", None)
            if text is not None:
                return json.loads(text)
        raise RemoteToolError(
            f"tool {tool_name} returned no text block: {result!r}"
        )
