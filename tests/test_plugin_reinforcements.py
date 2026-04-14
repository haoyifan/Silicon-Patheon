"""F.8: a plugin can spawn reinforcement units on_turn_start."""

from __future__ import annotations

from clash_of_odin.server.engine.rules import EndTurnAction, apply
from clash_of_odin.server.engine.scenarios import build_state
from clash_of_odin.server.engine.state import (
    Pos,
    Team,
    Unit,
    UnitStatus,
)
from clash_of_odin.server.engine.units import make_stats
from clash_of_odin.server.engine.state import UnitClass


def _spawn_on_turn_3(state, turn, team, **_):
    if turn == 2 and team == "red":
        stats = make_stats(UnitClass.KNIGHT)
        uid = "u_r_reinforcement_1"
        state.units[uid] = Unit(
            id=uid,
            owner=Team.RED,
            class_="knight",
            pos=Pos(3, 0),
            hp=stats.hp_max,
            status=UnitStatus.READY,
            stats=stats,
        )


def test_plugin_spawns_reinforcements():
    cfg = {
        "board": {"width": 6, "height": 6, "terrain": [], "forts": []},
        "armies": {
            "blue": [{"class": "knight", "pos": {"x": 0, "y": 0}}],
            "red": [{"class": "knight", "pos": {"x": 5, "y": 5}}],
        },
        "rules": {"max_turns": 10, "first_player": "blue"},
        "plugin_hooks": {"on_turn_start": ["spawn_on_turn_3"]},
    }
    state = build_state(cfg)
    state._plugin_namespace = {"spawn_on_turn_3": _spawn_on_turn_3}
    assert len(state.units) == 2
    apply(state, EndTurnAction())  # blue ends, red turn 1 (hook sees turn=1)
    assert len(state.units) == 2
    apply(state, EndTurnAction())  # red ends, blue turn 2
    apply(state, EndTurnAction())  # blue ends, red turn 2 → hook fires
    assert "u_r_reinforcement_1" in state.units
