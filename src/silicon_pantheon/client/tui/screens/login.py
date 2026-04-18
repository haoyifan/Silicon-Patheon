"""Login screen: gather server URL + player metadata, connect, transition.

Fields navigated via Tab (or Down) / Shift-Tab (Up). Enter submits.
On submit the ServerClient is constructed, initialized, and
set_player_metadata is called; success transitions to the Lobby.
Failures stay on this screen with an error banner.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from rich.align import Align
from rich.console import Group, RenderableType
from rich.panel import Panel
from rich.text import Text

from silicon_pantheon.client.locale import t
from silicon_pantheon.client.tui.app import Screen, TUIApp

if TYPE_CHECKING:
    from silicon_pantheon.client.tui.screens.lobby import LobbyScreen


import unicodedata


def _pad_label(s: str, width: int) -> str:
    """Pad to visual width, accounting for CJK double-width chars."""
    vw = sum(2 if unicodedata.east_asian_width(c) in ("W", "F") else 1 for c in s)
    return s + " " * max(0, width - vw)


@dataclass
class _Field:
    label: str
    value: str


class LoginScreen(Screen):
    def __init__(self, app: TUIApp):
        self.app = app
        lc = app.state.locale
        self._fields: list[_Field] = [
            _Field(t("login_fields.server_url", lc), app.state.server_url),
            _Field(t("login_fields.display_name", lc), app.state.display_name),
        ]
        self._active = 0
        self._connecting = False
        self._confirm = None

    def render(self) -> RenderableType:
        if self._confirm is not None:
            return self._confirm.render()
        lines: list[Text] = []
        title = Text(f"SiliconPantheon — {t('login_screen.title', self.app.state.locale)}", style="bold yellow")
        lines.append(title)
        lines.append(Text(""))
        for i, f in enumerate(self._fields):
            is_active = i == self._active
            marker = "➤" if is_active else " "
            label = Text(f"{marker} {_pad_label(f.label, 14)}", style="bold" if is_active else "dim")
            value_text = Text(f.value or t("login_empty", self.app.state.locale), style="white" if f.value else "dim italic")
            line = Text.assemble(label, Text("  "), value_text)
            lines.append(line)
        lines.append(Text(""))
        status = Text("")
        lc = self.app.state.locale
        if self._connecting:
            status.append(t("login_screen.connecting", lc), style="yellow")
        elif self.app.state.error_message:
            status.append(self.app.state.error_message, style="red")
        elif self.app.state.status_message:
            status.append(self.app.state.status_message, style="green")
        lines.append(status)
        lines.append(Text(""))
        keys = Text(t("login_screen.submit", lc), style="dim")
        lines.append(keys)

        body = Group(*lines)
        return Align.center(Panel(body, title=t("login_screen.title", lc), border_style="yellow"), vertical="middle")

    async def handle_key(self, key: str) -> Screen | None:
        if self._confirm is not None:
            close = await self._confirm.handle_key(key)
            if close:
                self._confirm = None
            return None
        if self._connecting:
            return None
        f = self._fields[self._active]
        if key == "esc":
            from silicon_pantheon.client.tui.screens.language_picker import LanguagePickerScreen
            return LanguagePickerScreen(self.app)
        if key == "q":
            from silicon_pantheon.client.tui.widgets import ConfirmModal
            from silicon_pantheon.client.locale import t
            async def _quit(yes: bool) -> None:
                if yes:
                    self.app.exit()
            self._confirm = ConfirmModal(
                prompt=t("lobby_quit.confirm", self.app.state.locale),
                on_confirm=_quit,
                locale=self.app.state.locale,
            )
            return None
        if key == "enter":
            # Submit if required fields are populated.
            return await self._submit()
        if key == "down" or key == "\t":
            self._active = (self._active + 1) % len(self._fields)
            return None
        if key == "up":
            self._active = (self._active - 1) % len(self._fields)
            return None
        if key == "backspace":
            f.value = f.value[:-1]
            return None
        # Ignore non-printable control keys; accept printable.
        if len(key) == 1 and key.isprintable():
            f.value = (f.value + key)[:120]
        return None

    async def _submit(self) -> Screen | None:
        lc = self.app.state.locale
        url = self._fields[0].value.strip()
        name = self._fields[1].value.strip()
        # Validate before connecting.
        if not url or not url.startswith(("http://", "https://")):
            self.app.state.error_message = t("login_fields.url_invalid", lc)
            return None
        if not name:
            self.app.state.error_message = t("login_fields.display_name_required", lc)
            return None
        self._connecting = True
        self.app.state.error_message = ""
        self.app.state.status_message = t("login_screen.connecting", lc)

        # Copy field values into shared state.
        self.app.state.server_url = url
        self.app.state.display_name = name
        # kind defaults to "ai"; provider and model are set later by
        # the ProviderAuthScreen (no longer collected on the login form).
        self.app.state.kind = "ai"

        # Late-import to avoid circular imports.
        from silicon_pantheon.client.tui.screens.provider_auth import ProviderAuthScreen

        try:
            await _connect_and_declare(self.app)
        except Exception as e:
            self._connecting = False
            self.app.state.error_message = f"{t('login_fields.connect_failed', self.app.state.locale)}: {e}"
            return None
        # Pipeline: login -> provider-auth -> lobby. ProviderAuthScreen
        # handles the resume-or-pick-fresh logic for LLM credentials.
        return ProviderAuthScreen(self.app)


async def _validate_url(url: str) -> None:
    """Fast pre-flight check: probe the URL before attempting the full
    MCP handshake. Catches DNS errors, wrong ports, and non-MCP servers
    in ~1s instead of hanging for 10s.

    MCP servers respond to GET with 405 Method Not Allowed (they only
    accept POST). A connection error or HTML response means the URL
    is wrong."""
    import httpx

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(url)
            # MCP endpoints return 405 on GET — that's correct.
            if r.status_code == 405:
                return  # looks like an MCP server
            # 200 with HTML = web page, not MCP
            ct = r.headers.get("content-type", "")
            if "html" in ct:
                raise ConnectionError(
                    f"URL returned a web page, not an MCP server. "
                    f"Expected format: http://host:port/mcp/"
                )
            # Other 2xx/3xx — might be OK, let MCP handshake decide
            return
    except httpx.ConnectError as e:
        raise ConnectionError(
            f"cannot connect to {url} — check host and port. "
            f"Expected format: http://host:port/mcp/"
        ) from e
    except httpx.ConnectTimeout:
        raise ConnectionError(
            f"connection timed out — server not responding. "
            f"Expected format: http://host:port/mcp/"
        )
    except ConnectionError:
        raise
    except Exception:
        # Other errors (SSL, etc.) — let MCP handshake handle it
        return


async def _connect_and_declare(app: TUIApp) -> None:
    """Open the ServerClient context, call set_player_metadata, start
    heartbeat. The client is retained on the app for later screens."""
    import asyncio as _aio

    from silicon_pantheon.client.transport import ServerClient

    # Fast pre-flight: catch bad URLs in ~1s instead of hanging.
    await _validate_url(app.state.server_url)

    # We need the ServerClient's context to stay open for the whole app
    # lifetime. The `ServerClient.connect` classmethod is an async ctx
    # manager that opens the SSE connection; we enter it manually and
    # rely on TUIApp.run to clean up on exit.
    ctx = ServerClient.connect(app.state.server_url)
    try:
        client = await _aio.wait_for(ctx.__aenter__(), timeout=10.0)
    except _aio.TimeoutError:
        raise ConnectionError(
            "MCP handshake timed out after 10s — server may not "
            "support MCP. Expected format: http://host:port/mcp/"
        )
    app.client = client

    async def _cleanup() -> None:
        await ctx.__aexit__(None, None, None)

    app._transport_cleanup = _cleanup  # type: ignore[attr-defined]

    from silicon_pantheon.shared.protocol import PROTOCOL_VERSION

    r = await client.call(
        "set_player_metadata",
        display_name=app.state.display_name,
        kind=app.state.kind,
        provider=app.state.provider,
        model=app.state.model,
        client_protocol_version=PROTOCOL_VERSION,
    )
    if not r.get("ok"):
        raise RuntimeError((r.get("error") or {}).get("message", "metadata rejected"))
    app.state.connection_id = client.connection_id
    await client.start_heartbeat()
