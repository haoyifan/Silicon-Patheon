"""Pain's Assault on Konoha — Naruto Sage Mode reinforcement at turn 10.

Turn 10: Naruto in Sage Mode spawns at the village gate (8, 13 is
impassable wall, so he appears just inside at 8, 11).

Guarded by a once-only flag so repeated on_turn_start invocations
are idempotent.
"""

from __future__ import annotations

from silicon_pantheon.server.engine.state import (
    Pos,
    Team,
    Unit,
    UnitStatus,
)
from silicon_pantheon.server.engine.scenarios import build_unit_stats, find_spawn_pos


_NARUTO_SPEC = {
    "display_name": "Naruto (Sage Mode)",
    "description": (
        "Naruto Uzumaki in Sage Mode. Infused with nature energy, "
        "his speed, strength, and senses are amplified beyond anything "
        "the Paths of Pain have faced. The strongest unit on the field."
    ),
    "hp_max": 40,
    "atk": 15,
    "defense": 6,
    "res": 8,
    "spd": 8,
    "move": 5,
    "rng_min": 1,
    "rng_max": 2,
    "glyph": "!",
    "color": "bright_yellow",
}

_NARUTO_SPAWN = (8, 11)


def naruto_reinforcement(state, turn: int, team: str, **_):
    """Called every on_turn_start. Spawns Naruto Sage Mode on
    turn 10 (one-shot)."""
    if turn != 10 or state.__dict__.get("_naruto_arrived"):
        return
    state.__dict__["_naruto_arrived"] = True
    uid = "u_b_naruto_sage_1"
    if uid in state.units:
        return
    x, y = _NARUTO_SPAWN
    stats = build_unit_stats("naruto_sage", _NARUTO_SPEC)
    spawn_pos = find_spawn_pos(state, Pos(x, y))
    state.units[uid] = Unit(
        id=uid,
        owner=Team.BLUE,
        class_="naruto_sage",
        pos=spawn_pos,
        hp=stats.hp_max,
        status=UnitStatus.READY,
        stats=stats,
    )
