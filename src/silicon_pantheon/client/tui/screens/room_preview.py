"""Room preview screen — shown when pressing 'p' in the lobby.

Displays the scenario description (story, difficulty, win conditions,
armies, units) plus room configuration (fog, teams, turn time, seats).
Esc returns to the lobby. Scrollable with j/k.
"""

from __future__ import annotations

from rich.align import Align
from rich.console import Group, RenderableType
from rich.panel import Panel
from rich.text import Text
from typing import Any

from silicon_pantheon.client.locale import t
from silicon_pantheon.client.tui.app import Screen, TUIApp
from silicon_pantheon.client.tui.scenario_display import (
    describe_win_condition,
    filter_win_conditions,
    localized_team,
)


class RoomPreviewScreen(Screen):
    def __init__(
        self,
        app: TUIApp,
        room_data: dict[str, Any],
        scenario_desc: dict[str, Any] | None = None,
    ):
        self.app = app
        self._room = room_data
        self._desc = scenario_desc or {}
        self._scroll = 0

    def render(self) -> RenderableType:
        lc = self.app.state.locale
        room = self._room
        desc = self._desc

        rows: list[RenderableType] = []

        # ---- Room config header ----
        scenario = room.get("scenario", "?")
        name = desc.get("name") or scenario
        rows.append(Text(name, style="bold yellow"))

        # Difficulty
        difficulty = desc.get("difficulty", 0)
        if difficulty:
            level_name = t(f"difficulty.{difficulty}", lc)
            diff_text = Text()
            diff_text.append(f"{t('difficulty.label', lc)}: ", style="bold")
            diff_text.append("★" * difficulty + "☆" * (5 - difficulty), style="yellow")
            diff_text.append(f" ({level_name})", style="dim")
            rows.append(diff_text)

        rows.append(Text(""))

        # Room settings
        config_text = Text()
        config_text.append(f"{t('room_status.fog_label', lc)}: ", style="bold")
        config_text.append(room.get("fog_of_war", "?"), style="white")
        config_text.append(f"   {t('room_status.teams_label', lc)}: ", style="bold")
        config_text.append(room.get("team_assignment", "?"), style="white")
        config_text.append(f"   {t('room_buttons.turn_time', lc)}: ", style="bold")
        config_text.append(f"{room.get('turn_time_limit_s', '?')}s", style="white")
        rows.append(config_text)

        # Seats
        seats = room.get("seats", {})
        for slot_id in ("a", "b"):
            seat = seats.get(slot_id, {})
            player = seat.get("player") or {}
            player_name = player.get("display_name") or t("room_player.empty", lc)
            model = player.get("model") or ""
            ready = "✓" if seat.get("ready") else "…"
            style = "cyan" if slot_id == "a" else "red"
            line = Text(f"  {slot_id} [{ready}] {player_name}", style=style)
            if model:
                line.append(f" ({model})", style="dim")
            rows.append(line)

        # ---- Scenario description ----
        story = (desc.get("description") or "").strip()
        if story:
            rows.append(Text(""))
            rows.append(Text(story))

        # Win conditions
        win_conds = desc.get("win_conditions") or []
        if win_conds:
            rows.append(Text(""))
            rows.append(Text(t("section.how_to_win", lc), style="bold"))
            for wc in filter_win_conditions(win_conds):
                rows.append(
                    Text(f"  • {describe_win_condition(wc, desc, lc)}", style="dim")
                )

        # Armies
        armies = desc.get("armies") or {}
        unit_classes = desc.get("unit_classes") or {}
        if armies:
            rows.append(Text(""))
            rows.append(Text(t("section.armies", lc), style="bold"))
            for owner in ("blue", "red"):
                units = armies.get(owner) or []
                if not units:
                    continue
                cls_counts: dict[str, int] = {}
                for u in units:
                    cls_counts[u.get("class", "?")] = cls_counts.get(u.get("class", "?"), 0) + 1
                def _label(slug: str) -> str:
                    spec = unit_classes.get(slug) or {}
                    return str(spec.get("display_name") or slug)
                summary = ", ".join(
                    f"{n}×{_label(c)}" if n > 1 else _label(c)
                    for c, n in cls_counts.items()
                )
                color = "cyan" if owner == "blue" else "red"
                rows.append(Text(f"  {localized_team(owner, lc)}: {summary}", style=color))

        # ---- Footer ----
        rows.append(Text(""))
        rows.append(Text("Esc back   j/k scroll", style="dim"))

        # ---- Scroll ----
        try:
            ch = self.app.console.height
        except Exception:
            ch = 30
        visible = max(1, ch - 4)
        max_scroll = max(0, len(rows) - visible)
        if self._scroll > max_scroll:
            self._scroll = max_scroll
        if self._scroll > 0:
            rows = rows[self._scroll:]

        return Align.center(
            Panel(Group(*rows), title=name, border_style="yellow", padding=(1, 3)),
            vertical="middle",
        )

    async def handle_key(self, key: str) -> Screen | None:
        if key in ("esc", "q"):
            from silicon_pantheon.client.tui.screens.lobby import LobbyScreen
            return LobbyScreen(self.app)
        if key in ("down", "j"):
            self._scroll += 1
            return None
        if key in ("up", "k"):
            self._scroll = max(0, self._scroll - 1)
            return None
        return None
