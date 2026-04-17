"""Battle of the Bastards — Knights of the Vale reinforcement.

Turn 10: six heavy cavalry from the Eyrie spawn at the south edge.
Sansa's letter worked. The Bolton encirclement breaks.

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
from silicon_pantheon.server.engine.scenarios import build_unit_stats


_VALE_KNIGHT_SPEC = {
    "display_name": "Knight of the Vale",
    "description": (
        "Heavy cavalry of the Eyrie. Fresh, armored, devastating "
        "on the charge."
    ),
    "hp_max": 28,
    "atk": 11,
    "defense": 7,
    "res": 4,
    "spd": 6,
    "move": 5,
    "rng_min": 1,
    "rng_max": 1,
    "glyph": "V",
    "color": "bright_cyan",
}

# Spawn positions — south edge of the 14×10 map, spread across the
# width so they can hit both flanks of the Bolton encirclement.
_VALE_SPAWNS = [
    (2, 9), (4, 9), (6, 9), (7, 9), (9, 9), (11, 9),
]


def vale_reinforcements(state, turn: int, team: str, **_):
    """Called every on_turn_start. Spawns Knights of the Vale on
    turn 10 (one-shot)."""
    if turn != 10 or state.__dict__.get("_vale_arrived"):
        return
    state.__dict__["_vale_arrived"] = True
    for i, (x, y) in enumerate(_VALE_SPAWNS, start=1):
        uid = f"u_b_vale_knight_{i}"
        if uid in state.units:
            continue
        # Skip tiles that are occupied (shouldn't happen at south
        # edge but defensive).
        if any(u.pos == Pos(x, y) for u in state.units.values()):
            continue
        stats = build_unit_stats("vale_knight", _VALE_KNIGHT_SPEC)
        state.units[uid] = Unit(
            id=uid,
            owner=Team.BLUE,
            class_="vale_knight",
            pos=Pos(x, y),
            hp=stats.hp_max,
            status=UnitStatus.READY,
            stats=stats,
        )
