"""Post-match screen stub — full implementation in 1d.6."""

from __future__ import annotations

from rich.align import Align
from rich.console import RenderableType
from rich.panel import Panel
from rich.text import Text

from clash_of_robots.client.tui.app import Screen, TUIApp


class PostMatchScreen(Screen):
    def __init__(self, app: TUIApp):
        self.app = app

    def render(self) -> RenderableType:
        gs = self.app.state.last_game_state or {}
        winner = gs.get("winner")
        reason = (gs.get("last_action") or {}).get("reason", "")
        banner = Text(f"Winner: {winner or '(draw)'}", style="bold green")
        if reason:
            banner.append(f"  reason={reason}", style="dim")
        body = Group_or_text(
            [
                banner,
                Text(""),
                Text("Post-match screen stub — 1d.6 adds replay download.", style="dim italic"),
                Text(""),
                Text("[q] quit", style="dim"),
            ]
        )
        return Align.center(Panel(body, title="match over", border_style="green"), vertical="middle")

    async def handle_key(self, key: str) -> Screen | None:
        if key == "q":
            self.app.exit()
        return None


def Group_or_text(items):  # small helper to avoid importing Group twice
    from rich.console import Group

    return Group(*items)
