"""Class stat tables — the canonical source for unit capabilities."""

from __future__ import annotations

from .state import UnitClass, UnitStats

CLASS_STATS: dict[UnitClass, UnitStats] = {
    UnitClass.KNIGHT: UnitStats(
        hp_max=30,
        atk=8,
        defense=7,
        res=2,
        spd=3,
        rng_min=1,
        rng_max=1,
        move=3,
        is_magic=False,
        can_enter_forest=True,
        can_enter_mountain=False,
        can_heal=False,
    ),
    UnitClass.ARCHER: UnitStats(
        hp_max=18,
        atk=9,
        defense=3,
        res=3,
        spd=5,
        rng_min=2,
        rng_max=3,
        move=4,
        is_magic=False,
        can_enter_forest=True,
        can_enter_mountain=True,
        can_heal=False,
    ),
    UnitClass.CAVALRY: UnitStats(
        hp_max=22,
        atk=7,
        defense=4,
        res=3,
        spd=7,
        rng_min=1,
        rng_max=1,
        move=6,
        is_magic=False,
        can_enter_forest=False,
        can_enter_mountain=False,
        can_heal=False,
    ),
    UnitClass.MAGE: UnitStats(
        hp_max=16,
        atk=8,
        defense=2,
        res=7,
        spd=4,
        rng_min=1,
        rng_max=2,
        move=4,
        is_magic=True,
        can_enter_forest=True,
        can_enter_mountain=True,
        can_heal=True,
        heal_amount=8,
    ),
}


def make_stats(cls: UnitClass) -> UnitStats:
    """Return a fresh copy of stats for the given class."""
    src = CLASS_STATS[cls]
    # UnitStats is mutable; we copy so per-unit effects don't leak into the class table.
    return UnitStats(
        hp_max=src.hp_max,
        atk=src.atk,
        defense=src.defense,
        res=src.res,
        spd=src.spd,
        rng_min=src.rng_min,
        rng_max=src.rng_max,
        move=src.move,
        is_magic=src.is_magic,
        can_enter_forest=src.can_enter_forest,
        can_enter_mountain=src.can_enter_mountain,
        can_heal=src.can_heal,
        heal_amount=src.heal_amount,
    )
