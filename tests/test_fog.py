"""Fog-of-war invariants and filter round-trips.

The filter is the single audit surface for "no info leak"; these
tests pin the invariants listed in viewer_filter.py's docstring.

Several tests place units by mutation rather than relying on a
scenario's stock positions — this isolates us from changes to
scenario geometry or the sight-stat values.
"""

from __future__ import annotations

from clash_of_robots.server.engine.scenarios import load_scenario
from clash_of_robots.server.engine.state import GameState, Pos, Team
from clash_of_robots.shared.fog import visible_tiles
from clash_of_robots.shared.viewer_filter import (
    ViewerContext,
    currently_visible,
    filter_state,
    filter_threat_map,
    filter_unit,
    update_ever_seen,
)


def _ctx(team: Team, mode: str, ever_seen=frozenset()):  # noqa: ANN001
    return ViewerContext(team=team, fog_mode=mode, ever_seen=ever_seen)  # type: ignore[arg-type]


def _spread_out(state: GameState) -> None:
    """Shove blue units into a corner and red into the opposite corner
    so they can't see each other regardless of sight stats."""
    w, h = state.board.width, state.board.height
    blue_positions = [Pos(0, 0), Pos(0, 1), Pos(1, 0)]
    red_positions = [Pos(w - 1, h - 1), Pos(w - 1, h - 2), Pos(w - 2, h - 1)]
    blue_iter = iter(blue_positions)
    red_iter = iter(red_positions)
    for u in list(state.units.values()):
        target = (
            next(blue_iter) if u.owner is Team.BLUE else next(red_iter)
        )
        u.pos = target


def test_visible_tiles_includes_own_units_tiles() -> None:
    state = load_scenario("01_tiny_skirmish")
    vis = visible_tiles(state, Team.BLUE)
    for u in state.units_of(Team.BLUE):
        assert u.pos in vis


def test_none_mode_is_identity() -> None:
    state = load_scenario("01_tiny_skirmish")
    ctx = _ctx(Team.BLUE, "none")
    filtered = filter_state(state, ctx)
    # In none mode, every unit on both teams is present.
    owners = {u["owner"] for u in filtered["units"]}
    assert owners == {"blue", "red"}


def test_classic_hides_out_of_sight_enemies() -> None:
    state = load_scenario("01_tiny_skirmish")
    _spread_out(state)
    ctx = _ctx(Team.BLUE, "classic")
    filtered = filter_state(state, ctx)
    owners = {u["owner"] for u in filtered["units"]}
    assert "blue" in owners
    assert "red" not in owners  # invisible when on opposite corners


def test_classic_ever_seen_reveals_past_terrain_not_units() -> None:
    state = load_scenario("01_tiny_skirmish")
    _spread_out(state)
    # Pretend blue's team once saw every tile on the board.
    all_tiles = frozenset(
        Pos(x, y) for x in range(state.board.width) for y in range(state.board.height)
    )
    ctx = _ctx(Team.BLUE, "classic", ever_seen=all_tiles)
    filtered = filter_state(state, ctx)
    # All tile terrain should be revealed (no "unknown" masks).
    types = {t["type"] for t in filtered["board"]["tiles"]}
    assert "unknown" not in types
    # But units out of current sight still hidden.
    owners = {u["owner"] for u in filtered["units"]}
    assert "red" not in owners


def test_line_of_sight_masks_more_than_classic() -> None:
    state = load_scenario("01_tiny_skirmish")
    # Build an ever_seen that mimics a few turns of exploration for classic.
    ever_seen = update_ever_seen(state, Team.BLUE, frozenset())

    classic = filter_state(state, _ctx(Team.BLUE, "classic", ever_seen=ever_seen))
    los = filter_state(state, _ctx(Team.BLUE, "line_of_sight"))

    known_classic = {
        (t["x"], t["y"]) for t in classic["board"]["tiles"] if t["type"] != "unknown"
    }
    known_los = {
        (t["x"], t["y"]) for t in los["board"]["tiles"] if t["type"] != "unknown"
    }
    # Classic reveals at least everything line-of-sight does.
    assert known_los <= known_classic


def test_filter_unit_hides_enemy_out_of_sight() -> None:
    state = load_scenario("01_tiny_skirmish")
    _spread_out(state)
    ctx = _ctx(Team.BLUE, "classic")
    # Pick a red unit.
    red = next(iter(state.units_of(Team.RED)))
    u_dict = {
        "id": red.id,
        "owner": red.owner.value,
        "pos": {"x": red.pos.x, "y": red.pos.y},
    }
    assert filter_unit(red.id, u_dict, state, ctx) is None


def test_filter_unit_shows_own_team() -> None:
    state = load_scenario("01_tiny_skirmish")
    ctx = _ctx(Team.BLUE, "classic")
    blue = next(iter(state.units_of(Team.BLUE)))
    u_dict = {
        "id": blue.id,
        "owner": blue.owner.value,
        "pos": {"x": blue.pos.x, "y": blue.pos.y},
    }
    assert filter_unit(blue.id, u_dict, state, ctx) is not None


def test_filter_threat_map_drops_invisible_enemies() -> None:
    state = load_scenario("01_tiny_skirmish")
    _spread_out(state)
    ctx = _ctx(Team.BLUE, "classic")
    # Synthesize a threat map where every tile is threatened by one red unit
    # that's out of blue's sight.
    red = next(iter(state.units_of(Team.RED)))
    fake = {"threats": {"0,0": [red.id], "1,1": [red.id]}}
    out = filter_threat_map(fake, state, ctx)
    # Nothing should survive because the enemy is invisible.
    assert out == {"threats": {}}


def test_currently_visible_matches_visible_tiles() -> None:
    state = load_scenario("01_tiny_skirmish")
    ctx = _ctx(Team.BLUE, "classic")
    assert currently_visible(state, ctx) == visible_tiles(state, Team.BLUE)
