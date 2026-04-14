"""Room screen panel framework + map cursor + unit card."""

from __future__ import annotations

import asyncio

import pytest
from rich.console import Console

from clash_of_odin.client.tui.app import SharedState
from clash_of_odin.client.tui.screens.room import (
    ActionsPanel,
    MapPanel,
    RoomScreen,
    UnitCard,
)


class _FakeApp:
    def __init__(self):
        self.state = SharedState()
        self.client = None
        self.exited = False

    def exit(self) -> None:
        self.exited = True


def _stub_room(app):
    app.state.room_id = "ROOM"
    app.state.slot = "a"
    app.state.last_room_state = {
        "room_id": "ROOM",
        "scenario": "01_tiny_skirmish",
        "fog_of_war": "none",
        "team_assignment": "fixed",
        "host_team": "blue",
        "status": "waiting_ready",
        "seats": {
            "a": {"player": {"display_name": "alice"}, "ready": False},
            "b": {"player": {"display_name": "bob"}, "ready": True},
        },
    }


def test_tab_cycles_focus_skipping_non_focusable():
    app = _FakeApp()
    _stub_room(app)
    screen = RoomScreen(app)
    # Built-in start: actions panel.
    assert screen._panels[screen._focus_idx] is screen.actions_panel
    # Tab → next focusable, which (Player & Description & Chat are
    # non-focusable in v1) should be the Map panel.
    asyncio.run(screen.handle_key("\t"))
    assert screen._panels[screen._focus_idx] is screen.map_panel
    # Tab again → cycles back to actions (others not focusable).
    asyncio.run(screen.handle_key("\t"))
    assert screen._panels[screen._focus_idx] is screen.actions_panel


def test_arrow_keys_only_affect_focused_panel():
    app = _FakeApp()
    _stub_room(app)
    screen = RoomScreen(app)
    # Focused on Actions: down moves the action cursor.
    initial_action = screen.actions_panel.focus
    asyncio.run(screen.handle_key("down"))
    assert screen.actions_panel.focus == initial_action + 1
    # Map cursor should not have moved.
    assert (screen.map_panel.cx, screen.map_panel.cy) == (0, 0)


def test_map_panel_cursor_navigates_with_arrows():
    app = _FakeApp()
    _stub_room(app)
    screen = RoomScreen(app)
    # Stub a 6x6 board.
    screen.scenario_preview = {
        "width": 6, "height": 6, "units": [], "forts": [],
    }
    # Focus the map panel.
    asyncio.run(screen.handle_key("\t"))
    assert screen._panels[screen._focus_idx] is screen.map_panel
    asyncio.run(screen.handle_key("right"))
    asyncio.run(screen.handle_key("right"))
    asyncio.run(screen.handle_key("down"))
    assert (screen.map_panel.cx, screen.map_panel.cy) == (2, 1)


def test_map_panel_cursor_wraps():
    app = _FakeApp()
    _stub_room(app)
    screen = RoomScreen(app)
    screen.scenario_preview = {"width": 4, "height": 4, "units": [], "forts": []}
    asyncio.run(screen.handle_key("\t"))
    asyncio.run(screen.handle_key("up"))
    assert screen.map_panel.cy == 3
    asyncio.run(screen.handle_key("left"))
    assert screen.map_panel.cx == 3


def test_enter_on_unit_opens_unit_card_modal():
    app = _FakeApp()
    _stub_room(app)
    screen = RoomScreen(app)
    screen.scenario_preview = {
        "width": 4, "height": 4,
        "units": [
            {
                "id": "u_b_knight_1", "owner": "blue", "class": "knight",
                "pos": {"x": 1, "y": 1},
                "hp": 30, "hp_max": 30, "atk": 8, "def": 7, "res": 2,
                "spd": 3, "move": 3, "rng": [1, 1],
            },
        ],
        "forts": [],
    }
    asyncio.run(screen.handle_key("\t"))  # focus map
    asyncio.run(screen.handle_key("right"))
    asyncio.run(screen.handle_key("down"))
    asyncio.run(screen.handle_key("enter"))
    assert isinstance(screen._modal, UnitCard)
    # Esc dismisses.
    asyncio.run(screen.handle_key("esc"))
    assert screen._modal is None


def test_unit_card_renders_stats_and_class_name():
    card = UnitCard(
        unit={
            "id": "u_b_sun_wukong_1", "owner": "blue", "class": "sun_wukong",
            "hp": 42, "hp_max": 42, "atk": 14, "def": 7, "res": 6,
            "spd": 9, "move": 5, "rng": [1, 1],
            "tags": ["hero", "monkey"],
        },
        class_spec={"description": "The Monkey King."},
    )
    console = Console(record=True, width=80)
    console.print(card.render())
    out = console.export_text()
    assert "sun_wukong" in out
    assert "The Monkey King" in out
    assert "42" in out  # hp
    assert "hero" in out and "monkey" in out


def test_focused_panel_gets_yellow_border():
    """Visual contract: the focused panel uses the bright_yellow style."""
    app = _FakeApp()
    _stub_room(app)
    screen = RoomScreen(app)
    console = Console(record=True, width=120)
    console.print(screen.render())
    # Switch to ANSI export to detect the highlight color.
    ansi = console.export_text(styles=True)
    # Yellow appears on the focused (Actions) panel border.
    assert "Actions" in ansi
