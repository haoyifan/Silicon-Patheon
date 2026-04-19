"""Tests for the lobby ranking view — Tab cycling, j/k navigation,
disclaimer banner — and the drill-down model details screen."""

from __future__ import annotations

import asyncio

from rich.console import Console

from silicon_pantheon.client.tui.app import SharedState
from silicon_pantheon.client.tui.screens.lobby import LobbyScreen
from silicon_pantheon.client.tui.screens.model_details import ModelDetailsScreen


class _FakeApp:
    def __init__(self):
        self.state = SharedState()
        self.client = None
        self.exited = False

    def exit(self) -> None:
        self.exited = True


def _render(screen, width: int = 200) -> str:
    console = Console(record=True, width=width)
    console.print(screen.render())
    return console.export_text()


def test_lobby_tab_cycles_views():
    app = _FakeApp()
    app.state.display_name = "alice"
    screen = LobbyScreen(app)
    assert screen._active_view == "rooms"
    asyncio.run(screen.handle_key("\t"))
    assert screen._active_view == "ranking"
    asyncio.run(screen.handle_key("\t"))
    assert screen._active_view == "rooms"


def test_lobby_ranking_jk_moves_selection_not_rooms():
    app = _FakeApp()
    app.state.display_name = "alice"
    app.state.last_rooms = [{"room_id": "r1"}, {"room_id": "r2"}, {"room_id": "r3"}]
    app.state.last_leaderboard = [
        {"model": "m1", "provider": "p", "games": 10, "wins": 5},
        {"model": "m2", "provider": "p", "games": 10, "wins": 3},
    ]
    screen = LobbyScreen(app)
    # Rooms view: j moves _selected.
    asyncio.run(screen.handle_key("j"))
    assert screen._selected == 1
    assert screen._ranking_selected == 0
    # Switch to ranking view.
    asyncio.run(screen.handle_key("\t"))
    asyncio.run(screen.handle_key("j"))
    assert screen._ranking_selected == 1
    assert screen._selected == 1  # unchanged
    asyncio.run(screen.handle_key("k"))
    assert screen._ranking_selected == 0


def test_lobby_ranking_disclaimer_rendered():
    app = _FakeApp()
    app.state.display_name = "alice"
    app.state.last_leaderboard = [
        {"model": "m1", "provider": "p", "games": 1, "wins": 1},
    ]
    screen = LobbyScreen(app)
    out = _render(screen)
    # Disclaimer text (or its prefix) should appear in rendered output.
    assert "Rankings" in out or "true capability" in out


def test_lobby_ranking_selection_marker_visible_when_focused():
    app = _FakeApp()
    app.state.display_name = "alice"
    app.state.last_leaderboard = [
        {"model": "first", "provider": "p", "games": 5, "wins": 3},
        {"model": "second", "provider": "p", "games": 5, "wins": 2},
    ]
    screen = LobbyScreen(app)
    # Focus ranking, select 2nd entry.
    asyncio.run(screen.handle_key("\t"))
    asyncio.run(screen.handle_key("j"))
    out = _render(screen)
    assert "first" in out
    assert "second" in out
    # The marker "➤" should appear on the selected row.
    assert "➤" in out


def test_model_details_handles_missing_client():
    app = _FakeApp()
    app.client = None
    screen = ModelDetailsScreen(app, model="m1", provider="p")
    asyncio.run(screen._fetch())
    assert screen._loaded is True
    assert screen._error


def test_model_details_esc_returns_to_lobby():
    app = _FakeApp()
    screen = ModelDetailsScreen(app, model="m1", provider="p")
    next_screen = asyncio.run(screen.handle_key("esc"))
    assert next_screen is not None
    assert next_screen.__class__.__name__ == "LobbyScreen"


def test_model_details_renders_empty_state():
    app = _FakeApp()
    screen = ModelDetailsScreen(app, model="m1", provider="p")
    screen._loaded = True
    screen._details = {}
    screen._h2h = []
    screen._scenarios = []
    out = _render(screen)
    assert "m1" in out
    assert "Head-to-Head" in out or "Opponent" in out


def test_model_details_renders_with_data():
    app = _FakeApp()
    screen = ModelDetailsScreen(app, model="claude-opus-4-7", provider="anthropic")
    screen._loaded = True
    screen._details = {
        "model": "claude-opus-4-7",
        "provider": "anthropic",
        "games": 10,
        "wins": 6,
        "losses": 3,
        "draws": 1,
        "win_pct": 60.0,
        "total_tokens": 1_200_000,
        "tokens_per_win": 200_000,
        "total_tool_calls": 400,
        "total_errors": 8,
        "error_rate_pct": 2.0,
        "avg_think_time_s": 4.3,
        "max_think_time_s": 42.1,
        "avg_units_killed": 3.2,
        "avg_units_lost": 2.1,
        "avg_match_duration_s": 180.0,
    }
    screen._h2h = [
        {"opponent": "gpt-4o", "provider": "openai", "games": 5, "wins": 3, "losses": 2, "draws": 0, "avg_turns": 14.2},
    ]
    screen._scenarios = [
        {"scenario": "03_thermopylae", "games": 4, "wins": 3, "losses": 1, "draws": 0},
        {"scenario": "04_cannae", "games": 6, "wins": 3, "losses": 2, "draws": 1},
    ]
    out = _render(screen)
    assert "claude-opus-4-7" in out
    assert "gpt-4o" in out
    assert "thermopylae" in out or "03_thermopylae" in out
    # Aggregate stats show up
    assert "60.0%" in out or "60%" in out
