"""Journey to the West plugin: turn-10 bridge ambush."""

from __future__ import annotations

from clash_of_odin.server.engine.state import (
    Pos,
    Team,
    Unit,
    UnitStatus,
)


def spawn_ambush(state, turn: int, team: str, **_):
    """On turn 10, summon two extra skeletons near the bridge to make
    the middle crossing hairier. Only fires once — subsequent calls
    are no-ops because the ids already exist."""
    if turn != 10 or team != "red":
        return
    if "u_r_ambush_1" in state.units:
        return
    # Find a live skeleton to copy stats from. If every skeleton is
    # already dead, give up — there's no clean source for the right
    # numbers and we'd rather skip the ambush than spawn knights with
    # the wrong stats (which an earlier version of this code did when
    # it fell back on next(iter(state.units)).stats).
    skel_stats = None
    for u in state.units.values():
        if u.class_ == "skeleton":
            skel_stats = u.stats
            break
    if skel_stats is None:
        return
    spawns = [("u_r_ambush_1", Pos(7, 3)), ("u_r_ambush_2", Pos(7, 5))]
    for uid, pos in spawns:
        # Skip if tile occupied.
        if any(u.pos == pos for u in state.units.values()):
            continue
        state.units[uid] = Unit(
            id=uid,
            owner=Team.RED,
            class_="skeleton",
            pos=pos,
            hp=skel_stats.hp_max,
            status=UnitStatus.READY,
            stats=skel_stats,
        )
