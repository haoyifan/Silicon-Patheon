"""Plugin-driven terrain effect: a tile calls a scenario Python fn
on end_turn to alter the occupying unit's HP.
"""

from __future__ import annotations

from silicon_pantheon.server.engine.rules import EndTurnAction, apply
from silicon_pantheon.server.engine.scenarios import build_state
from silicon_pantheon.server.engine.state import Team


def test_lethal_terrain_removes_unit_and_records_death():
    """Regression: lethal swamp damage used to leave a hp=0 zombie in
    state.units instead of removing the unit. Now mirrors attack: the
    unit is deleted and recorded in dead_unit_ids."""
    cfg = {
        "board": {
            "width": 4, "height": 4,
            "terrain": [{"x": 0, "y": 1, "type": "lava"}],
            "forts": [],
        },
        "terrain_types": {"lava": {"heals": -999}},
        "armies": {
            "blue": [{"class": "knight", "pos": {"x": 0, "y": 1}}],
            "red":  [{"class": "knight", "pos": {"x": 3, "y": 3}}],
        },
        "rules": {"max_turns": 10, "first_player": "blue"},
    }
    state = build_state(cfg)
    blue_id = next(u.id for u in state.units_of(Team.BLUE))
    apply(state, EndTurnAction())
    assert blue_id not in state.units, "lethal terrain should remove the unit"
    assert blue_id in state.dead_unit_ids


def test_plugin_terrain_deals_damage():
    cfg = {
        "board": {
            "width": 4,
            "height": 4,
            "terrain": [{"x": 0, "y": 1, "type": "poison"}],
            "forts": [],
        },
        "terrain_types": {
            "poison": {"effects_plugin": "poison_damage"},
        },
        "armies": {
            "blue": [{"class": "knight", "pos": {"x": 0, "y": 1}}],
            "red": [{"class": "knight", "pos": {"x": 3, "y": 3}}],
        },
        "rules": {"max_turns": 10, "first_player": "blue"},
    }
    state = build_state(cfg)
    state._plugin_namespace = {
        "poison_damage": lambda state, unit, tile, hook: {"hp_delta": -4}
    }
    blue_unit = next(iter(state.units_of(Team.BLUE)))
    start_hp = blue_unit.hp
    apply(state, EndTurnAction())
    assert blue_unit.hp == start_hp - 4
