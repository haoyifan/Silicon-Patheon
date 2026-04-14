"""Plugins for the Strait of Hormuz scenario.

Two callables:

  - hormuz_win_check: the sole authoritative win-condition. Blue
    wins iff a blue unit occupies the uranium-bunker tile AND
    Khamenei is dead. Red wins when turn > max_turns without that
    compound goal met (i.e. Iran held the line for 10 turns).

  - sea_mine_effect: the contact-mine terrain hook. Any unit ending
    its turn on a sea_mine tile takes 6 HP. One-shot — the mine
    detonates and is replaced with normal water.
"""

from __future__ import annotations

from silicon_pantheon.server.engine.state import Pos, Team, Tile
from silicon_pantheon.server.engine.win_conditions.base import WinResult

# Coordinates of the uranium bunker must match config.yaml.
_BUNKER_POS = Pos(15, 5)
_KHAMENEI_ID = "u_r_khamenei_1"


def hormuz_win_check(state, hook: str, **_):
    """Authoritative win rule for this scenario.

    Called by the plugin win-condition at end_turn. Returns a
    WinResult on victory, or None to let the match continue.

    Victory lattice:
      - blue: on_bunker AND khamenei_dead, before turn budget exhausts
      - red:  turn > max_turns and blue has not met the compound goal
      - red:  both blue VIP leaders are dead (operation cancelled)

    Protect_unit rules for each individual VIP are listed in
    win_conditions as defensive redundancy, but they fire on a
    single-death and flip the match to red immediately. This
    plugin therefore only needs to cover the "both dead" /
    "turn-budget" shapes.
    """
    if hook != "end_turn":
        return None

    dead = getattr(state, "dead_unit_ids", set())
    khamenei_dead = _KHAMENEI_ID in dead

    # Blue victory lane.
    blue_on_bunker = any(
        u.pos == _BUNKER_POS for u in state.units_of(Team.BLUE)
    )
    if blue_on_bunker and khamenei_dead:
        return WinResult(
            winner="blue",
            reason="uranium_seized_and_khamenei_killed",
            details={
                "bunker": _BUNKER_POS.to_dict(),
                "khamenei_id": _KHAMENEI_ID,
            },
        )

    # Red victory lane: Iran holds the line for the full ten turns.
    # state.turn increments when play wraps back to first_player,
    # so after blue's and red's turn-10 halves state.turn == 11.
    if state.turn > state.max_turns:
        return WinResult(
            winner="red",
            reason="iran_held_the_line",
            details={"khamenei_dead": khamenei_dead},
        )

    return None


def sea_mine_effect(state, unit, tile, hook: str, **_):
    """Terrain effect for sea_mine tiles.

    Fires at end_turn for whichever team just ended. Any unit
    standing on a mine takes 6 damage. The mine then detonates
    (one-shot) and the tile flips to plain water so the next
    unit to cross gets a clear lane.
    """
    if hook != "end_turn":
        return {"hp_delta": 0}
    # Detonate exactly once: replace the tile with water before the
    # rules-engine's hp_delta application so the damage is the
    # mine's final word.
    pos = unit.pos
    state.board.tiles[pos] = Tile(
        pos=pos,
        type="water",
        passable=True,
        glyph="~",
        color="blue",
    )
    return {"hp_delta": -6}
