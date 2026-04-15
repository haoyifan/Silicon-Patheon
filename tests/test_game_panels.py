"""Game screen panel framework + map cursor + coach panel."""

from __future__ import annotations

import asyncio

from rich.console import Console

from silicon_pantheon.client.tui.app import SharedState
from silicon_pantheon.client.tui.screens.game import (
    CoachPanel,
    GameMapPanel,
    GameScreen,
    ReasoningPanel,
)
from silicon_pantheon.client.tui.screens.room import UnitCard


class _FakeApp:
    def __init__(self):
        self.state = SharedState()
        self.client = None
        self.exited = False

    def exit(self) -> None:
        self.exited = True


def _stub_state(app, *, units=None, board_w=6, board_h=6, my_team="blue"):
    app.state.last_game_state = {
        "turn": 1, "max_turns": 20,
        "active_player": my_team, "you": my_team, "status": "in_progress",
        "board": {"width": board_w, "height": board_h, "tiles": []},
        "units": units or [],
        "rules": {"max_turns": 20},
    }


def test_player_panel_roster_shows_header_status_and_dead_state():
    from rich.console import Console
    from silicon_pantheon.client.tui.screens.game import PlayerPanel

    app = _FakeApp()
    _stub_state(
        app,
        units=[
            {"id": "u_b_1", "owner": "blue", "class": "knight",
             "hp": 20, "hp_max": 30, "alive": True, "status": "moved",
             "pos": {"x": 0, "y": 0}},
            {"id": "u_r_1", "owner": "red", "class": "archer",
             "hp": 0, "hp_max": 18, "alive": False,
             "pos": {"x": 3, "y": 3}},
        ],
    )
    screen = GameScreen(app)
    screen.state = app.state.last_game_state
    console = Console(record=True, width=60)
    console.print(PlayerPanel(screen).render(focused=False))
    out = console.export_text()
    # Header columns.
    assert "Unit" in out
    assert "HP" in out
    assert "Status" in out
    # Live unit's status text.
    assert "moved" in out
    # Dead unit's "dead" marker.
    assert "dead" in out


def test_game_on_enter_clears_thoughts_buffer():
    """Regression: the reasoning panel kept showing the previous
    match's thoughts because SharedState.thoughts survives screen
    transitions (PostMatchScreen needs it for the transcript). The
    new game's on_enter should wipe it so reasoning starts empty."""
    app = _FakeApp()
    app.state.thoughts.extend(
        [(f"00:00:0{i}", "blue", f"prior match thought {i}") for i in range(3)]
    )
    _stub_state(app)
    screen = GameScreen(app)
    asyncio.run(screen.on_enter(app))
    assert len(app.state.thoughts) == 0


def test_player_panel_scrolls_when_focused():
    from silicon_pantheon.client.tui.screens.game import PlayerPanel

    app = _FakeApp()
    _stub_state(
        app,
        units=[
            {"id": f"u{i}", "owner": "blue", "class": "knight",
             "hp": 30, "hp_max": 30, "alive": True, "pos": {"x": 0, "y": i}}
            for i in range(6)
        ],
    )
    screen = GameScreen(app)
    screen.state = app.state.last_game_state
    panel = PlayerPanel(screen)
    assert panel.scroll == 0
    asyncio.run(panel.handle_key("down"))
    assert panel.scroll == 1
    asyncio.run(panel.handle_key("up"))
    assert panel.scroll == 0
    # Can't go below 0.
    asyncio.run(panel.handle_key("up"))
    assert panel.scroll == 0


def test_tab_cycles_through_four_panels_in_order():
    app = _FakeApp()
    screen = GameScreen(app)
    _stub_state(app)
    screen.state = app.state.last_game_state
    assert screen._panels[screen._focus_idx] is screen.map_panel
    expected = ["PlayerPanel", "ReasoningPanel", "CoachPanel", "GameMapPanel"]
    for want in expected:
        asyncio.run(screen.handle_key("\t"))
        assert type(screen._panels[screen._focus_idx]).__name__ == want


def test_map_cursor_only_responds_when_map_focused():
    app = _FakeApp()
    screen = GameScreen(app)
    _stub_state(app)
    screen.state = app.state.last_game_state
    # Map is default-focused.
    asyncio.run(screen.handle_key("right"))
    assert screen.map_panel.cx == 1
    # Tab to Actions; arrows now move action focus, not the map cursor.
    asyncio.run(screen.handle_key("\t"))
    map_x_before = screen.map_panel.cx
    asyncio.run(screen.handle_key("right"))
    assert screen.map_panel.cx == map_x_before


def test_enter_on_unit_in_game_opens_inline_unit_card():
    app = _FakeApp()
    screen = GameScreen(app)
    _stub_state(
        app,
        units=[
            {
                "id": "u_b_knight_1", "owner": "blue", "class": "knight",
                "pos": {"x": 2, "y": 2}, "hp": 30, "hp_max": 30, "alive": True,
                "atk": 8, "def": 7, "res": 2, "spd": 3, "move": 3, "rng": [1, 1],
            },
        ],
    )
    screen.state = app.state.last_game_state
    asyncio.run(screen.handle_key("right"))
    asyncio.run(screen.handle_key("right"))
    asyncio.run(screen.handle_key("down"))
    asyncio.run(screen.handle_key("down"))
    asyncio.run(screen.handle_key("enter"))
    assert isinstance(screen.unit_card, UnitCard)
    # Esc dismisses the card without exiting.
    asyncio.run(screen.handle_key("esc"))
    assert screen.unit_card is None


def test_coach_panel_captures_typing_when_focused():
    app = _FakeApp()
    screen = GameScreen(app)
    _stub_state(app)
    screen.state = app.state.last_game_state
    # Tab to coach (Map → Player → Reasoning → Coach).
    for _ in range(3):
        asyncio.run(screen.handle_key("\t"))
    assert screen._panels[screen._focus_idx] is screen.coach_panel
    for ch in "push the cavalry":
        asyncio.run(screen.handle_key(ch))
    assert screen.coach_panel.buffer == "push the cavalry"
    # 'q' goes into the buffer instead of quitting.
    asyncio.run(screen.handle_key("q"))
    assert screen.coach_panel.buffer.endswith("q")
    assert app.exited is False
    # Esc clears the buffer.
    asyncio.run(screen.handle_key("esc"))
    assert screen.coach_panel.buffer == ""


def test_coach_tab_only_releases_when_buffer_empty():
    """If a user is mid-message, Tab should NOT silently cycle them
    away to a different panel — they could be typing 'tab' as part of
    a longer thought."""
    app = _FakeApp()
    screen = GameScreen(app)
    _stub_state(app)
    screen.state = app.state.last_game_state
    for _ in range(3):
        asyncio.run(screen.handle_key("\t"))
    # Type something, then try to Tab away → no-op while buffer non-empty.
    for ch in "hi":
        asyncio.run(screen.handle_key(ch))
    asyncio.run(screen.handle_key("\t"))
    assert screen._panels[screen._focus_idx] is screen.coach_panel
    # Clear and Tab — now we leave.
    asyncio.run(screen.handle_key("esc"))
    asyncio.run(screen.handle_key("\t"))
    assert screen._panels[screen._focus_idx] is screen.map_panel


def test_reasoning_panel_vim_keys_route_correctly():
    """Vim-style scroll keys on a read-only panel: ctrl-f/ctrl-b for
    page, ctrl-d/ctrl-u for half-page, shift-g for tail (here = 0
    because ReasoningPanel is tail-anchored), gg for oldest."""
    app = _FakeApp()
    app.console = Console(width=120, height=30)
    _stub_state(app)
    screen = GameScreen(app)
    screen.state = app.state.last_game_state
    panel = screen.reasoning_panel

    # Seed enough thoughts to give max_back room.
    app.state.thoughts.extend(
        [(f"00:00:0{i}", "blue", f"line {i}") for i in range(20)]
    )

    # Tail anchor: line_offset starts at 0.
    assert panel.line_offset == 0

    # ctrl-b: page back into history (offset increases).
    asyncio.run(panel.handle_key("ctrl-b"))
    assert panel.line_offset == 12

    # ctrl-f: page forward toward tail (offset decreases).
    asyncio.run(panel.handle_key("ctrl-f"))
    assert panel.line_offset == 0

    # ctrl-u from tail does nothing useful (we go BACK 6, into history).
    asyncio.run(panel.handle_key("ctrl-u"))
    assert panel.line_offset == 6

    # ctrl-d: half-page forward toward tail (decreases offset by 6).
    asyncio.run(panel.handle_key("ctrl-d"))
    assert panel.line_offset == 0

    # gg: two-press latch jumps to oldest. line_offset gets a huge
    # value that render() will clamp.
    asyncio.run(panel.handle_key("g"))
    assert panel._gg_primed is True
    assert panel.line_offset == 0  # first g is no-op
    asyncio.run(panel.handle_key("g"))
    assert panel._gg_primed is False
    assert panel.line_offset > 100  # large; render clamps

    # G (shift-g) snaps back to tail.
    asyncio.run(panel.handle_key("shift-g"))
    assert panel.line_offset == 0


def test_reasoning_panel_pins_view_while_user_scrolled_up():
    """Default: panel tails the latest thought, so k/j at offset 0 is
    reading newest-first on every render. Once the user scrolls up
    (offset > 0), the view must freeze on the content the user is
    reading — new thoughts appended to the tail should not yank the
    view away. Pressing '0' drops back to live tail."""
    app = _FakeApp()
    # Stub the console width/height that the panel queries via
    # self.screen.app.console — _FakeApp has no console attribute
    # by default, so construct one with the Rich stub.
    app.console = Console(width=120, height=30)
    _stub_state(app)

    screen = GameScreen(app)
    screen.state = app.state.last_game_state

    panel = screen.reasoning_panel

    # First thought populates the tail.
    app.state.thoughts.append(("12:00:01", "blue", "A\nB\nC\nD\nE"))
    first = panel.render(focused=False).renderable.plain
    assert "A" in first and "E" in first, "tail should show the thought"

    # User scrolls up — view shows older content.
    panel.line_offset = 3
    pinned_before = panel.render(focused=False).renderable.plain

    # New thought arrives while scrolled. The pinning logic in
    # render() bumps line_offset by the number of appended lines so
    # the same content slice stays visible.
    app.state.thoughts.append(("12:00:05", "blue", "Z1\nZ2\nZ3"))
    pinned_after = panel.render(focused=False).renderable.plain

    assert pinned_after == pinned_before, (
        "view shifted while user was scrolled up; pinning is broken"
    )

    # '0' returns to live tail, revealing the newest thought.
    asyncio.run(panel.handle_key("0"))
    live = panel.render(focused=False).renderable.plain
    assert "Z1" in live, "returning to tail should reveal newest content"


def test_reasoning_panel_scroll_is_focus_gated():
    app = _FakeApp()
    screen = GameScreen(app)
    _stub_state(app)
    screen.state = app.state.last_game_state
    app.state.thoughts.extend(
        [(f"00:00:0{i}", "blue", f"thought {i}") for i in range(5)]
    )
    # Map is focused; up arrow moves the map cursor, not reasoning offset.
    before = screen.reasoning_panel.line_offset
    asyncio.run(screen.handle_key("up"))
    assert screen.reasoning_panel.line_offset == before
    # Tab Map→Player→Reasoning.
    for _ in range(2):
        asyncio.run(screen.handle_key("\t"))
    asyncio.run(screen.handle_key("up"))
    # k/j now move by 3 logical lines (not 1 entry).
    assert screen.reasoning_panel.line_offset == before + 3


def test_apply_vim_scroll_helper_covers_all_keys():
    """The shared helper used by every read-only scrollable panel."""
    from silicon_pantheon.client.tui.panels import apply_vim_scroll

    # j / down → +1, k / up → -1
    assert apply_vim_scroll("j", current=5) == 6
    assert apply_vim_scroll("down", current=5) == 6
    assert apply_vim_scroll("k", current=5) == 4
    assert apply_vim_scroll("up", current=5) == 4

    # Half-page (default page_size=12 → half=6)
    assert apply_vim_scroll("ctrl-d", current=10) == 16
    assert apply_vim_scroll("ctrl-u", current=10) == 4

    # Full page
    assert apply_vim_scroll("ctrl-f", current=10) == 22
    assert apply_vim_scroll("pgdown", current=10) == 22
    assert apply_vim_scroll("ctrl-b", current=20) == 8
    assert apply_vim_scroll("pgup", current=20) == 8

    # G / end / home
    assert apply_vim_scroll("shift-g", current=5, bottom=99) == 99
    assert apply_vim_scroll("end", current=5, bottom=99) == 99
    assert apply_vim_scroll("home", current=5) == 0

    # gg latch: first 'g' primes, second 'g' jumps to top.
    gg = [False]
    assert apply_vim_scroll("g", current=42, gg_state=gg) == 42  # primed
    assert gg == [True]
    assert apply_vim_scroll("g", current=42, gg_state=gg) == 0  # fired
    assert gg == [False]

    # gg latch resets on any other key.
    gg = [True]
    assert apply_vim_scroll("j", current=5, gg_state=gg) == 6
    assert gg == [False]

    # Lower-bound clamp: can't go below 0.
    assert apply_vim_scroll("k", current=0) == 0
    assert apply_vim_scroll("ctrl-u", current=2) == 0

    # Unrecognized keys → None (caller falls through).
    assert apply_vim_scroll("enter", current=5) is None
    assert apply_vim_scroll("q", current=5) is None
