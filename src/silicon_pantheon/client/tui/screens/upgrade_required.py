"""Dedicated screen shown when the client/server version handshake
finds an incompatible gap.

Two variants:
  - kind="client_too_old" — server rejected us; user should upgrade.
  - kind="server_too_old" — server is older than we support; user
    should ask the server operator to update (or point at a newer
    server URL).

Shown in place of the lobby after a failed set_player_metadata. Keys:
  - q / Esc — exit the client
  - Enter   — back to the login screen (to change server URL or retry)
"""

from __future__ import annotations

from rich.align import Align
from rich.console import Group, RenderableType
from rich.panel import Panel
from rich.text import Text

from silicon_pantheon.client.locale import t
from silicon_pantheon.client.tui.app import Screen, TUIApp


class UpgradeRequiredScreen(Screen):
    def __init__(
        self,
        app: TUIApp,
        *,
        kind: str,
        message: str,
        data: dict,
    ) -> None:
        self.app = app
        self.kind = kind  # "client_too_old" | "server_too_old"
        self.message = message
        self.data = data

    async def tick(self) -> None:
        return None

    async def handle_key(self, key: str) -> Screen | None:
        if key in ("q", "esc"):
            self.app.exit()
            return None
        if key == "enter":
            # Close the transport we opened during the failed connect
            # before bouncing back to login — otherwise the next
            # connect attempt stacks a second transport on top.
            cleanup = getattr(self.app, "_transport_cleanup", None)
            if cleanup is not None:
                try:
                    await cleanup()
                except Exception:
                    pass
                self.app._transport_cleanup = None
                self.app.client = None
            from silicon_pantheon.client.tui.screens.login import LoginScreen
            return LoginScreen(self.app)
        return None

    def render(self) -> RenderableType:
        lc = self.app.state.locale
        title_key = (
            "upgrade.client_too_old_title"
            if self.kind == "client_too_old"
            else "upgrade.server_too_old_title"
        )
        hint_key = (
            "upgrade.client_too_old_hint"
            if self.kind == "client_too_old"
            else "upgrade.server_too_old_hint"
        )

        body_lines: list[RenderableType] = [
            Text(t(title_key, lc), style="bold red"),
            Text(""),
            Text(self.message, style="yellow"),
            Text(""),
            Text(t(hint_key, lc), style="dim"),
        ]

        # Include the upgrade command if the server sent one.
        cmd = self.data.get("upgrade_command") if isinstance(self.data, dict) else None
        if cmd:
            body_lines.append(Text(""))
            body_lines.append(Text(str(cmd), style="bold cyan"))

        body_lines.append(Text(""))
        body_lines.append(Text(""))
        body_lines.append(Text(t("upgrade.footer", lc), style="dim italic"))

        panel = Panel(
            Group(*body_lines),
            title=t("upgrade.panel_title", lc),
            border_style="red",
            padding=(1, 3),
        )
        return Align.center(panel, vertical="middle")
