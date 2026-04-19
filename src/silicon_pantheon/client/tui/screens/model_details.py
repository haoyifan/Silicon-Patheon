"""Drill-down screen for a single model.

Opened from the lobby ranking view (Tab to ranking, select a row with
j/k, press Enter). Shows:
  - head-to-head table (per opponent: games, W/L/D, win%, avg turns)
  - per-scenario table (scenario: games, W/L/D, win%)
  - aggregated stats panel (tokens-per-win, error rate, etc.)

Esc returns to the lobby.
"""

from __future__ import annotations

import logging
from typing import Any

from rich.console import Group, RenderableType
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from silicon_pantheon.client.locale import t
from silicon_pantheon.client.tui.app import Screen, TUIApp

log = logging.getLogger("silicon.tui.model_details")


class ModelDetailsScreen(Screen):
    def __init__(self, app: TUIApp, *, model: str, provider: str):
        self.app = app
        self.model = model
        self.provider = provider
        self._details: dict[str, Any] = {}
        self._h2h: list[dict[str, Any]] = []
        self._scenarios: list[dict[str, Any]] = []
        self._loaded = False
        self._error: str = ""

    async def on_enter(self, app: TUIApp) -> None:
        await self._fetch()

    async def tick(self) -> None:
        return None

    async def _fetch(self) -> None:
        if self.app.client is None:
            self._error = t("errors.not_connected", self.app.state.locale)
            self._loaded = True
            return
        try:
            r = await self.app.client.call(
                "get_model_details", model=self.model, provider=self.provider
            )
        except Exception as e:
            self._error = f"get_model_details failed: {e}"
            self._loaded = True
            return
        if not r.get("ok"):
            err = (r.get("error") or {}).get("message", "get_model_details rejected")
            self._error = err
            self._loaded = True
            return
        result = r.get("result") or r
        self._details = result.get("details") or {}
        self._h2h = result.get("head_to_head") or []
        self._scenarios = result.get("per_scenario") or []
        self._loaded = True

    async def handle_key(self, key: str) -> Screen | None:
        if key in ("esc", "q"):
            from silicon_pantheon.client.tui.screens.lobby import LobbyScreen
            return LobbyScreen(self.app)
        return None

    def render(self) -> RenderableType:
        lc = self.app.state.locale
        title = f"{t('head_to_head.title', lc)} — {self.model}"
        header = Text(title, style="bold cyan")
        subtitle = Text(
            f"{self.provider}" if self.provider else "",
            style="dim",
        )

        if not self._loaded:
            body = Group(header, subtitle, Text(""), Text(t("head_to_head.loading", lc)))
            return Panel(body, border_style="cyan")
        if self._error:
            body = Group(
                header,
                subtitle,
                Text(""),
                Text(self._error, style="red"),
                Text(""),
                Text(t("head_to_head.back_hint", lc), style="dim"),
            )
            return Panel(body, border_style="red")

        stats_panel = self._render_stats_panel(lc)
        h2h_panel = self._render_h2h_panel(lc)
        scen_panel = self._render_scenario_panel(lc)
        back = Text(t("head_to_head.back_hint", lc), style="dim italic")
        body = Group(header, subtitle, Text(""), stats_panel, Text(""), h2h_panel, Text(""), scen_panel, Text(""), back)
        return Panel(body, border_style="cyan")

    def _render_stats_panel(self, lc: str) -> RenderableType:
        d = self._details
        if not d:
            return Panel(
                Text(t("head_to_head.no_matches", lc), style="dim"),
                border_style="dim",
                title=t("head_to_head.stats_title", lc),
            )

        def _fmt_tokens_per_win(v: Any) -> str:
            if v is None:
                return "—"
            if v >= 1_000_000:
                return f"{v / 1_000_000:.2f}M"
            if v >= 1000:
                return f"{v / 1000:.1f}k"
            return f"{int(v)}"

        def _fmt_duration(v: float) -> str:
            if not v:
                return "—"
            if v < 60:
                return f"{v:.0f}s"
            m = int(v // 60)
            s = int(v % 60)
            return f"{m}m{s:02d}s"

        kv = Table.grid(padding=(0, 2))
        kv.add_column(style="dim")
        kv.add_column(justify="right")
        kv.add_column(style="dim")
        kv.add_column(justify="right")

        kv.add_row(
            t("head_to_head.stat_games", lc), str(d.get("games", 0)),
            t("head_to_head.stat_win_pct", lc), f"{d.get('win_pct', 0):.1f}%",
        )
        kv.add_row(
            t("head_to_head.stat_wins", lc),
            f"{d.get('wins', 0)}",
            t("head_to_head.stat_tokens_per_win", lc),
            _fmt_tokens_per_win(d.get("tokens_per_win")),
        )
        kv.add_row(
            t("head_to_head.stat_losses", lc), str(d.get("losses", 0)),
            t("head_to_head.stat_error_rate", lc), f"{d.get('error_rate_pct', 0):.2f}%",
        )
        kv.add_row(
            t("head_to_head.stat_draws", lc), str(d.get("draws", 0)),
            t("head_to_head.stat_avg_think", lc), f"{d.get('avg_think_time_s', 0):.1f}s",
        )
        avg_killed = d.get("avg_units_killed")
        avg_lost = d.get("avg_units_lost")
        kv.add_row(
            t("head_to_head.stat_avg_killed", lc),
            f"{avg_killed:.1f}" if avg_killed is not None else "—",
            t("head_to_head.stat_avg_lost", lc),
            f"{avg_lost:.1f}" if avg_lost is not None else "—",
        )
        kv.add_row(
            t("head_to_head.stat_max_think", lc), f"{d.get('max_think_time_s', 0):.1f}s",
            t("head_to_head.stat_avg_duration", lc), _fmt_duration(d.get("avg_match_duration_s", 0)),
        )

        return Panel(kv, border_style="yellow", title=t("head_to_head.stats_title", lc))

    def _render_h2h_panel(self, lc: str) -> RenderableType:
        tbl = Table(expand=True, show_lines=False, header_style="bold", padding=(0, 1))
        tbl.add_column(t("head_to_head.col_opponent", lc), overflow="fold")
        tbl.add_column(t("head_to_head.col_games", lc), justify="right")
        tbl.add_column(t("head_to_head.col_wins", lc), justify="right")
        tbl.add_column(t("head_to_head.col_losses", lc), justify="right")
        tbl.add_column(t("head_to_head.col_draws", lc), justify="right")
        tbl.add_column(t("head_to_head.col_win_pct", lc), justify="right")
        tbl.add_column(t("head_to_head.col_avg_turns", lc), justify="right")

        if not self._h2h:
            tbl.add_row(t("head_to_head.no_opponents", lc), "", "", "", "", "", "")
        else:
            for entry in self._h2h:
                games = entry.get("games", 0)
                wins = entry.get("wins", 0)
                win_pct = f"{wins / games * 100:.0f}%" if games else "—"
                tbl.add_row(
                    entry.get("opponent", "?"),
                    str(games),
                    str(wins),
                    str(entry.get("losses", 0)),
                    str(entry.get("draws", 0)),
                    win_pct,
                    f"{entry.get('avg_turns', 0):.1f}",
                )
        return Panel(tbl, border_style="green", title=t("head_to_head.h2h_title", lc))

    def _render_scenario_panel(self, lc: str) -> RenderableType:
        tbl = Table(expand=True, show_lines=False, header_style="bold", padding=(0, 1))
        tbl.add_column(t("head_to_head.col_scenario", lc), overflow="fold")
        tbl.add_column(t("head_to_head.col_games", lc), justify="right")
        tbl.add_column(t("head_to_head.col_wins", lc), justify="right")
        tbl.add_column(t("head_to_head.col_losses", lc), justify="right")
        tbl.add_column(t("head_to_head.col_draws", lc), justify="right")
        tbl.add_column(t("head_to_head.col_win_pct", lc), justify="right")

        if not self._scenarios:
            tbl.add_row(t("head_to_head.no_scenarios", lc), "", "", "", "", "")
        else:
            for entry in self._scenarios:
                games = entry.get("games", 0)
                wins = entry.get("wins", 0)
                win_pct = f"{wins / games * 100:.0f}%" if games else "—"
                scenario_raw = entry.get("scenario", "?")
                cached = self.app.state.scenario_cache.get(scenario_raw)
                label = (cached.get("name") if cached else None) or scenario_raw
                tbl.add_row(
                    label,
                    str(games),
                    str(wins),
                    str(entry.get("losses", 0)),
                    str(entry.get("draws", 0)),
                    win_pct,
                )
        return Panel(tbl, border_style="magenta", title=t("head_to_head.scenarios_title", lc))
