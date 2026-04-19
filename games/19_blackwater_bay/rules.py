"""Blackwater Bay — Tywin + Tyrell reinforcement at turn 5.

Turn 5: Tywin Lannister and four Tyrell knights arrive. Tywin
body-blocks the Mud Gate corridor; the knights crash into the
eastern walls. Previously arrived at turn 8, but games rarely
reach that far, so the reinforcement was effectively never firing.

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


_TYRELL_KNIGHT_SPEC = {
    "display_name": "Tyrell Knight",
    "description": (
        "Heavy cavalry of Highgarden, arriving with Tywin Lannister. "
        "Fresh, armored, and devastating."
    ),
    "hp_max": 26,
    "atk": 10,
    "defense": 7,
    "res": 3,
    "spd": 6,
    "move": 5,
    "rng_min": 1,
    "rng_max": 1,
    "glyph": "K",
    "color": "bright_red",
}

# Mirrors the `tywin` unit_classes entry in config.yaml. Kept in
# sync by hand; if you retune one, retune the other.
_TYWIN_SPEC = {
    "display_name": "Tywin Lannister",
    "description": (
        "The Old Lion. Lord of Casterly Rock. Arrives at turn 5 with "
        "fresh cavalry from the Kingsroad. The battle turns when his "
        "banner appears."
    ),
    "hp_max": 28,
    "atk": 10,
    "defense": 7,
    "res": 5,
    "spd": 6,
    "move": 5,
    "rng_min": 1,
    "rng_max": 1,
    "tags": ["hero", "cavalry", "reinforcement"],
    "sight": 4,
    "glyph": "T",
    "color": "bright_red",
}

_TYRELL_SPAWNS = [
    (13, 2), (13, 8), (12, 1), (12, 9),
]

# Mud Gate corridor, body-blocking the blue breach path at y=7
# just behind the gate at (12, 7). find_spawn_pos will BFS to the
# nearest passable tile if this is impassable or occupied.
_TYWIN_SPAWN = (13, 7)
_TYWIN_UID = "u_r_tywin_1"


def tyrell_reinforcements(state, turn: int, team: str, **_):
    """Called every on_turn_start. Spawns Tywin + four Tyrell knights
    on turn 5 (one-shot)."""
    if turn != 5 or state.__dict__.get("_tyrell_arrived"):
        return
    state.__dict__["_tyrell_arrived"] = True

    # Tywin first — he claims the (13, 7) body-block before the
    # knights start filling nearby tiles via find_spawn_pos.
    if _TYWIN_UID not in state.units:
        tywin_stats = build_unit_stats("tywin", _TYWIN_SPEC)
        tywin_pos = find_spawn_pos(state, Pos(*_TYWIN_SPAWN))
        state.units[_TYWIN_UID] = Unit(
            id=_TYWIN_UID,
            owner=Team.RED,
            class_="tywin",
            pos=tywin_pos,
            hp=tywin_stats.hp_max,
            status=UnitStatus.READY,
            stats=tywin_stats,
        )

    for i, (x, y) in enumerate(_TYRELL_SPAWNS, start=1):
        uid = f"u_r_tyrell_knight_{i}"
        if uid in state.units:
            continue
        stats = build_unit_stats("tyrell_knight", _TYRELL_KNIGHT_SPEC)
        spawn_pos = find_spawn_pos(state, Pos(x, y))
        state.units[uid] = Unit(
            id=uid,
            owner=Team.RED,
            class_="tyrell_knight",
            pos=spawn_pos,
            hp=stats.hp_max,
            status=UnitStatus.READY,
            stats=stats,
        )
