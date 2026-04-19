"""Department of Mysteries plugin — Order of the Phoenix reinforcements.

Turn 8: order_reinforcements — 4 Order members (Sirius, Lupin, Tonks,
                                Moody) spawn at the corridor entrances
                                for blue.

Guarded by a once-only flag stored on the state so repeated
on_turn_start invocations are idempotent.
"""

from __future__ import annotations

from silicon_pantheon.server.engine.state import (
    Pos,
    Team,
    Unit,
    UnitStatus,
)
from silicon_pantheon.server.engine.scenarios import build_unit_stats, find_spawn_pos


def order_reinforcements(state, turn: int, team: str, **_):
    """Turn 8: the Order of the Phoenix arrives with 4 reinforcements."""
    if turn != 8 or state.__dict__.get("_order_arrived"):
        return
    state.__dict__["_order_arrived"] = True

    spawns = [
        # Sirius charges into the Time Room
        ("sirius", 4, 6),
        # Lupin bursts through the Death Chamber doorway
        ("lupin", 9, 6),
        # Tonks drops in behind the DA line along the west flank
        ("tonks", 1, 7),
        # Moody storms up through the Hall of Prophecy
        ("moody", 1, 3),
    ]
    for class_name, x, y in spawns:
        uid = f"u_b_{class_name}_1"
        if uid in state.units:
            continue
        spec = _CLASS_SPECS[class_name]
        stats = build_unit_stats(class_name, spec)
        spawn_pos = find_spawn_pos(state, Pos(x, y))
        state.units[uid] = Unit(
            id=uid, owner=Team.BLUE, class_=class_name,
            pos=spawn_pos, hp=stats.hp_max,
            status=UnitStatus.READY, stats=stats,
        )


_CLASS_SPECS = {
    "sirius": {
        "hp_max": 26, "atk": 11, "defense": 4, "res": 6,
        "spd": 6, "rng_min": 1, "rng_max": 2, "move": 4,
        "is_magic": True,
        "glyph": "S", "color": "white",
        "display_name": "Sirius Black",
        "description": "Harry's godfather. Fights with reckless joy.",
    },
    "lupin": {
        "hp_max": 24, "atk": 10, "defense": 4, "res": 6,
        "spd": 5, "rng_min": 1, "rng_max": 2, "move": 3,
        "is_magic": True,
        "glyph": "r", "color": "yellow",
        "display_name": "Remus Lupin",
        "description": "Werewolf, former professor, precise duelist.",
    },
    "tonks": {
        "hp_max": 22, "atk": 10, "defense": 3, "res": 5,
        "spd": 6, "rng_min": 1, "rng_max": 2, "move": 4,
        "is_magic": True,
        "glyph": "T", "color": "magenta",
        "display_name": "Nymphadora Tonks",
        "description": "Metamorphmagus Auror. Clumsy off-duty, lethal on.",
    },
    "moody": {
        "hp_max": 28, "atk": 11, "defense": 5, "res": 7,
        "spd": 4, "rng_min": 1, "rng_max": 3, "move": 3,
        "is_magic": True,
        "glyph": "X", "color": "bright_yellow",
        "display_name": "Alastor 'Mad-Eye' Moody",
        "description": "Retired Auror. His magical eye sees through walls.",
    },
}
