"""Declarative win-conditions framework tests.

Covers:
  - build_conditions() resolves DSL type strings to rule instances
  - default_conditions() returns the legacy 3-rule stack
  - reach_tile fires when the right team's unit lands on the pos
  - protect_unit fires when the VIP dies
  - reach_goal_line fires when any unit crosses
  - unknown type raises
"""

from __future__ import annotations

import pytest

from silicon_pantheon.server.engine.rules import EndTurnAction, apply
from silicon_pantheon.server.engine.state import (
    Board,
    GameState,
    GameStatus,
    Pos,
    Team,
    Tile,
    Unit,
    UnitStatus,
)
from silicon_pantheon.server.engine.units import make_stats
from silicon_pantheon.server.engine.state import UnitClass
from silicon_pantheon.server.engine.win_conditions import (
    build_conditions,
    default_conditions,
)
from silicon_pantheon.server.engine.win_conditions.rules import (
    EliminateAllEnemyUnits,
    MaxTurnsDraw,
    ProtectUnit,
    ReachGoalLine,
    ReachTile,
    SeizeEnemyFort,
)


def _make_state(
    units: dict[str, Unit],
    *,
    first_player: Team = Team.BLUE,
    width: int = 8,
    height: int = 8,
) -> GameState:
    board = Board(width=width, height=height, tiles={})
    return GameState(
        game_id="g_test",
        turn=1,
        max_turns=30,
        active_player=first_player,
        first_player=first_player,
        board=board,
        units=units,
    )


def _mkunit(uid: str, team: Team, pos: Pos, cls: UnitClass = UnitClass.KNIGHT) -> Unit:
    stats = make_stats(cls)
    return Unit(
        id=uid,
        owner=team,
        class_=cls.value,
        pos=pos,
        hp=stats.hp_max,
        status=UnitStatus.READY,
        stats=stats,
    )


def test_default_conditions_has_three_rules():
    rules = default_conditions()
    assert len(rules) == 3
    assert isinstance(rules[0], SeizeEnemyFort)
    assert isinstance(rules[1], EliminateAllEnemyUnits)
    assert isinstance(rules[2], MaxTurnsDraw)


def test_build_conditions_resolves_types():
    rules = build_conditions([
        {"type": "reach_tile", "team": "blue", "pos": {"x": 5, "y": 5}},
        {"type": "protect_unit", "unit_id": "u_b_infantry_1", "owning_team": "blue"},
    ])
    assert isinstance(rules[0], ReachTile)
    assert rules[0].team == "blue"
    assert isinstance(rules[1], ProtectUnit)


def test_build_conditions_unknown_type_raises():
    with pytest.raises(ValueError, match="unknown win_condition type"):
        build_conditions([{"type": "nonsense_rule"}])


def test_reach_tile_fires_on_end_turn():
    blue = _mkunit("u_b_1", Team.BLUE, Pos(5, 5))
    red = _mkunit("u_r_1", Team.RED, Pos(0, 0))
    state = _make_state({blue.id: blue, red.id: red})
    state._win_conditions = build_conditions([
        {"type": "reach_tile", "team": "blue", "pos": {"x": 5, "y": 5}},
    ])
    result = apply(state, EndTurnAction())
    assert result["winner"] == "blue"
    assert result["reason"] == "reach_tile"
    assert state.status is GameStatus.GAME_OVER


def test_reach_tile_does_not_fire_when_wrong_team():
    blue = _mkunit("u_b_1", Team.BLUE, Pos(0, 0))
    red = _mkunit("u_r_1", Team.RED, Pos(5, 5))
    state = _make_state({blue.id: blue, red.id: red})
    state._win_conditions = build_conditions([
        {"type": "reach_tile", "team": "blue", "pos": {"x": 5, "y": 5}},
    ])
    result = apply(state, EndTurnAction())
    assert result["winner"] is None
    assert state.status is not GameStatus.GAME_OVER


def test_protect_unit_fires_when_vip_killed_in_combat():
    """Regression: protect_unit used to silently no-op when the VIP
    was actually killed (because attack deletes the unit from the
    dict, and the rule's old `state.units.get(...) is None` branch
    treated 'missing' as 'not yet dead'). Now dead_unit_ids carries
    the death record across removal."""
    from silicon_pantheon.server.engine.rules import AttackAction
    from silicon_pantheon.server.engine.scenarios import build_state

    cfg = {
        "board": {"width": 4, "height": 4, "terrain": [], "forts": []},
        "unit_classes": {
            "vip":    {"hp_max": 1,  "atk": 1,  "defense": 0, "res": 0, "spd": 1, "move": 3},
            "killer": {"hp_max": 30, "atk": 99, "defense": 5, "res": 5, "spd": 9, "move": 3},
        },
        "armies": {
            "blue": [
                {"class": "vip",    "pos": {"x": 1, "y": 1}},
                {"class": "vip",    "pos": {"x": 0, "y": 0}},  # second blue so elimination doesn't fire
            ],
            "red":  [{"class": "killer", "pos": {"x": 1, "y": 2}}],
        },
        "rules": {"max_turns": 10, "first_player": "red"},
        "win_conditions": [
            {"type": "protect_unit", "unit_id": "u_b_vip_1", "owning_team": "blue"},
            {"type": "eliminate_all_enemy_units"},
            {"type": "max_turns_draw"},
        ],
    }
    state = build_state(cfg)
    apply(state, AttackAction(unit_id="u_r_killer_1", target_id="u_b_vip_1"))
    assert "u_b_vip_1" not in state.units
    assert "u_b_vip_1" in state.dead_unit_ids
    result = apply(state, EndTurnAction())
    assert result["winner"] == "red"
    assert result["reason"] == "vip_lost"


def test_protect_unit_fires_when_vip_missing():
    # VIP already dead (not in state.units).
    red = _mkunit("u_r_1", Team.RED, Pos(5, 5))
    state = _make_state({red.id: red})
    state._win_conditions = build_conditions([
        {"type": "protect_unit", "unit_id": "u_b_vip", "owning_team": "blue"},
    ])
    # protect_unit keys off `state.units.get(...)` — missing is treated
    # as alive (None). Add a dead-by-hp VIP to trigger.
    vip = _mkunit("u_b_vip", Team.BLUE, Pos(0, 0))
    vip.hp = 0
    state.units[vip.id] = vip
    result = apply(state, EndTurnAction())
    assert result["winner"] == "red"
    assert result["reason"] == "vip_lost"


def test_reach_goal_line_fires_on_axis():
    blue = _mkunit("u_b_1", Team.BLUE, Pos(3, 7))
    state = _make_state({blue.id: blue})
    state._win_conditions = build_conditions([
        {"type": "reach_goal_line", "team": "blue", "axis": "y", "value": 7},
    ])
    result = apply(state, EndTurnAction())
    assert result["winner"] == "blue"
    assert result["reason"] == "reach_goal_line"


def test_reach_goal_line_fires_when_unit_has_gone_past_the_line():
    """Regression: default "crosses" semantic triggers when a unit is
    past the line, not only exactly on it. Previous == check would
    fail a red unit at x=0 even when the goal line was x=1, because
    it had "overshot" into the Greek rear."""
    # Red team of two: one mostly-starting at x=9 (east), one that
    # has overshot to x=0 past the goal line at x=1. Median starting
    # position is on the east side → direction inferred as "<=".
    r1 = _mkunit("u_r_east", Team.RED, Pos(9, 3))
    r2 = _mkunit("u_r_crossed", Team.RED, Pos(0, 6))
    state = _make_state({r1.id: r1, r2.id: r2})
    state.active_player = Team.RED
    state._win_conditions = build_conditions([
        {"type": "reach_goal_line", "team": "red", "axis": "x", "value": 1},
    ])
    result = apply(state, EndTurnAction())
    assert result["winner"] == "red", (
        "red unit at x=0 should win when the line is x=1 — "
        "'crosses' means reached OR past"
    )


def test_reach_goal_line_exact_mode_still_requires_equality():
    """Legacy scenarios that explicitly want the exact-line semantic
    can opt in with direction: 'exact' — useful if a scenario
    genuinely rewards landing on a single row, not crossing."""
    # Blue needs to land exactly on y=7. Unit at y=8 (past) should
    # NOT trigger under "exact".
    blue = _mkunit("u_b_1", Team.BLUE, Pos(3, 8))
    state = _make_state({blue.id: blue})
    state._win_conditions = build_conditions([
        {
            "type": "reach_goal_line",
            "team": "blue",
            "axis": "y",
            "value": 7,
            "direction": "exact",
        },
    ])
    result = apply(state, EndTurnAction())
    assert result.get("winner") != "blue"


def test_protect_unit_survives_fires_at_turn_cap_when_vip_alive():
    """If the VIP is still alive when turn > max_turns, the protector
    wins (NOT a draw). Complement to protect_unit's VIP-dies-loss."""
    blue = _mkunit("u_b_henry", Team.BLUE, Pos(0, 0))
    red = _mkunit("u_r_1", Team.RED, Pos(5, 5))
    state = _make_state({blue.id: blue, red.id: red})
    state.max_turns = 3
    state.turn = 4  # already past the cap
    state._win_conditions = build_conditions([
        {"type": "protect_unit_survives",
         "unit_id": "u_b_henry", "owning_team": "blue"},
        {"type": "max_turns_draw"},  # backstop — must not fire first
    ])
    result = apply(state, EndTurnAction())
    assert result["winner"] == "blue"
    assert result["reason"] == "protect_survived"
    assert state.status is GameStatus.GAME_OVER


def test_protect_unit_survives_silent_before_cap():
    """Pre-cap the rule must NOT fire — match continues."""
    blue = _mkunit("u_b_henry", Team.BLUE, Pos(0, 0))
    red = _mkunit("u_r_1", Team.RED, Pos(5, 5))
    state = _make_state({blue.id: blue, red.id: red})
    state.max_turns = 10
    state.turn = 3
    state._win_conditions = build_conditions([
        {"type": "protect_unit_survives",
         "unit_id": "u_b_henry", "owning_team": "blue"},
    ])
    result = apply(state, EndTurnAction())
    assert result["winner"] is None
    assert state.status is not GameStatus.GAME_OVER


def test_scenario_without_protect_unit_survives_still_draws_at_cap():
    """Guard: scenarios that don't opt in to the new rule keep the
    legacy max_turns_draw behavior. A future refactor must NOT
    change that."""
    blue = _mkunit("u_b_1", Team.BLUE, Pos(0, 0))
    red = _mkunit("u_r_1", Team.RED, Pos(5, 5))
    state = _make_state({blue.id: blue, red.id: red})
    state.max_turns = 3
    state.turn = 4  # past cap
    state._win_conditions = build_conditions([
        {"type": "eliminate_all_enemy_units"},
        {"type": "max_turns_draw"},
    ])
    result = apply(state, EndTurnAction())
    assert result["winner"] is None  # draw
    assert result["reason"] == "max_turns"


def test_protect_unit_survives_order_matters_before_max_turns_draw():
    """When both rules are declared, survives must come FIRST in the
    YAML or max_turns_draw fires first (returns draw) and wins the
    race. Pin the ordering contract."""
    blue = _mkunit("u_b_henry", Team.BLUE, Pos(0, 0))
    red = _mkunit("u_r_1", Team.RED, Pos(5, 5))
    state = _make_state({blue.id: blue, red.id: red})
    state.max_turns = 3
    state.turn = 4

    # WRONG order — draw beats survives → scenario authors who mis-
    # order get a draw, not a survive-win.
    state._win_conditions = build_conditions([
        {"type": "max_turns_draw"},
        {"type": "protect_unit_survives",
         "unit_id": "u_b_henry", "owning_team": "blue"},
    ])
    result = apply(state, EndTurnAction())
    assert result["winner"] is None  # max_turns_draw beat it

    # Reset and try with CORRECT order.
    blue2 = _mkunit("u_b_henry", Team.BLUE, Pos(0, 0))
    red2 = _mkunit("u_r_2", Team.RED, Pos(5, 5))
    state2 = _make_state({blue2.id: blue2, red2.id: red2})
    state2.max_turns = 3
    state2.turn = 4
    state2._win_conditions = build_conditions([
        {"type": "protect_unit_survives",
         "unit_id": "u_b_henry", "owning_team": "blue"},
        {"type": "max_turns_draw"},
    ])
    result2 = apply(state2, EndTurnAction())
    assert result2["winner"] == "blue"


def test_agincourt_scenario_uses_protect_unit_survives():
    """The 06_agincourt scenario must declare protect_unit_survives
    before max_turns_draw. Smoke-test that the YAML change stuck."""
    from silicon_pantheon.server.engine.scenarios import load_scenario
    from silicon_pantheon.server.engine.win_conditions.rules import (
        ProtectUnitSurvives, MaxTurnsDraw,
    )

    state = load_scenario("06_agincourt")
    types = [type(r).__name__ for r in state._win_conditions]
    assert "ProtectUnitSurvives" in types, (
        f"agincourt missing ProtectUnitSurvives: got {types}"
    )
    # Ordering: survives must appear before max_turns_draw or the
    # draw fires first.
    i_survives = types.index("ProtectUnitSurvives")
    i_draw = types.index("MaxTurnsDraw")
    assert i_survives < i_draw, (
        "protect_unit_survives must come before max_turns_draw"
    )


def test_scenario_load_sets_win_conditions_attribute():
    """load_scenario should attach _win_conditions to the state."""
    from silicon_pantheon.server.engine.scenarios import load_scenario

    state = load_scenario("01_tiny_skirmish")
    assert hasattr(state, "_win_conditions")
    assert len(state._win_conditions) >= 1
