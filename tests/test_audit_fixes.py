"""Regressions for the second-pass audit fixes.

Covers:
  - plugin win-rule exception is contained, not propagated
  - terrain effects_plugin exception is contained, not propagated
  - path traversal via scenario name is rejected
  - unit position validation (overlap + off-board)
"""

from __future__ import annotations

import pytest

from silicon_pantheon.server.engine.rules import EndTurnAction, apply
from silicon_pantheon.server.engine.scenarios import (
    _is_safe_scenario_name,
    build_state,
    load_scenario,
)


def _base_cfg() -> dict:
    return {
        "board": {"width": 4, "height": 4, "terrain": [], "forts": []},
        "armies": {
            "blue": [{"class": "knight", "pos": {"x": 0, "y": 0}}],
            "red":  [{"class": "knight", "pos": {"x": 3, "y": 3}}],
        },
        "rules": {"max_turns": 10, "first_player": "blue"},
    }


def test_plugin_win_rule_exception_does_not_crash_end_turn():
    cfg = _base_cfg()
    cfg["win_conditions"] = [
        {"type": "plugin", "module": "rules", "check_fn": "broken"},
        {"type": "max_turns_draw"},
    ]
    state = build_state(cfg)

    def broken(state, hook, **kw):
        raise RuntimeError("intentional")

    state._plugin_namespace = {"broken": broken}
    # Should NOT raise — engine treats plugin failure as no-result.
    result = apply(state, EndTurnAction())
    assert result["winner"] is None


def test_terrain_effects_plugin_exception_does_not_crash_end_turn():
    cfg = {
        "board": {
            "width": 4, "height": 4,
            "terrain": [{"x": 0, "y": 0, "type": "weird"}],
            "forts": [],
        },
        "terrain_types": {"weird": {"effects_plugin": "broken"}},
        "armies": {
            "blue": [{"class": "knight", "pos": {"x": 0, "y": 0}}],
            "red":  [{"class": "knight", "pos": {"x": 3, "y": 3}}],
        },
        "rules": {"max_turns": 10, "first_player": "blue"},
    }
    state = build_state(cfg)
    state._plugin_namespace = {
        "broken": lambda *a, **k: (_ for _ in ()).throw(ValueError("nope"))
    }
    # Should not raise; unit's HP unchanged.
    blue = next(iter(state.units_of(state.active_player)))
    start_hp = blue.hp
    apply(state, EndTurnAction())
    assert blue.hp == start_hp


def test_unsafe_scenario_names_rejected():
    bad = ["", ".", "..", "a/b", "..\\foo", "../etc", ".hidden", "a\\b"]
    for n in bad:
        assert not _is_safe_scenario_name(n), f"should be unsafe: {n!r}"
    good = ["01_tiny_skirmish", "journey_to_the_west", "myMap", "a-b", "_test_plugin"]
    for n in good:
        assert _is_safe_scenario_name(n), f"should be safe: {n!r}"


def test_load_scenario_rejects_path_traversal():
    with pytest.raises(ValueError, match="unsafe scenario name"):
        load_scenario("../../etc/passwd")


def test_overlapping_unit_positions_rejected():
    cfg = _base_cfg()
    cfg["armies"]["blue"] = [
        {"class": "knight", "pos": {"x": 1, "y": 1}},
        {"class": "archer", "pos": {"x": 1, "y": 1}},
    ]
    with pytest.raises(ValueError, match="share starting position"):
        build_state(cfg)


def test_off_board_unit_position_rejected():
    cfg = _base_cfg()
    cfg["armies"]["blue"] = [{"class": "knight", "pos": {"x": 99, "y": 99}}]
    with pytest.raises(ValueError, match="off-board"):
        build_state(cfg)
