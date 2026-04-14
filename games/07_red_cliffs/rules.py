"""Red Cliffs plugin — fire spreads along the chained ship line.

The historical attack: Huang Gai feigns defection, sails his oil-
soaked ships into the chained northern fleet, and on the borrowed
east wind the fire jumps from deck to deck. Most of Cao Cao's army
burns or drowns.

Mechanic:
  - Starting turn 5 (the "east wind" turn), if Huang Gai (or any
    blue hero) is alive and adjacent to a `ship` tile, that ship
    catches fire — its tile type changes to `burning_ship`.
  - Each subsequent turn the fire spreads to one more adjacent
    ship tile in either direction along the chain.
  - Any unit standing on a burning_ship tile takes 6 HP/turn.
  - Burning ships stop being passable for any unit (they're
    sinking).

The state mutation is simple — we patch state.board.tiles directly.
The damage is delivered by replacing the tile type with one the
engine's end_turn loop already knows how to handle (the heals/damage
field). For the fire damage we attach an effects_plugin to the
burning_ship type so each end_turn ticks down occupant HP.
"""

from __future__ import annotations

from clash_of_odin.server.engine.state import Pos, Tile, Team

# How far the fire has spread (number of ship tiles consumed).
_STATE_KEY = "_red_cliffs_fire_state"


def light_fire(state, turn: int, team: str, **_):
    """Called every on_turn_start. Lights / spreads the fire."""
    if turn < 5:
        return
    fire = state.__dict__.setdefault(
        _STATE_KEY,
        {"started": False, "front_x": None, "back_x": None},
    )

    # Find Huang Gai (or any alive Wu hero) adjacent to a ship tile
    # to seed the fire.
    if not fire["started"]:
        seed = _find_seed_ship(state)
        if seed is None:
            return
        _ignite(state, seed)
        fire["started"] = True
        fire["front_x"] = seed.x
        fire["back_x"] = seed.x
        return

    # Spread one tile in each direction along the chain (y=4 and y=5,
    # x=10..14). The chain forms a 2-row band; spreading "outward"
    # means the smallest unburnt x to the left and largest to the right.
    fx = fire["front_x"]
    bx = fire["back_x"]
    if fx is not None and fx + 1 <= 14:
        _ignite_column(state, fx + 1)
        fire["front_x"] = fx + 1
    if bx is not None and bx - 1 >= 10:
        _ignite_column(state, bx - 1)
        fire["back_x"] = bx - 1


def _find_seed_ship(state):
    """Return a ship Pos adjacent to Huang Gai (or any blue hero on
    the river edge). Returns None if none yet."""
    fire_lighters = [
        u for u in state.units.values()
        if u.alive and u.owner is Team.BLUE and "fire_lighter" in (u.stats.tags or [])
    ]
    if not fire_lighters:
        # Fall back to any blue hero on the south bank — flexible
        # in case Huang Gai dies before lighting.
        fire_lighters = [
            u for u in state.units.values()
            if u.alive and u.owner is Team.BLUE
        ]
    for u in fire_lighters:
        for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            adj = Pos(u.pos.x + dx, u.pos.y + dy)
            tile = state.board.tiles.get(adj)
            if tile is not None and tile.type == "ship":
                return adj
    return None


def _ignite(state, pos: Pos) -> None:
    """Convert one ship tile into a burning_ship tile."""
    old = state.board.tiles.get(pos)
    if old is None or old.type != "ship":
        return
    state.board.tiles[pos] = Tile(
        pos=pos,
        type="burning_ship",
        # -6 HP/turn at end_turn for the occupant. Negative `heals`
        # is the engine's idiom for damage tiles.
        heals=-6,
        passable=False,
        glyph="!",
        color="bright_red",
    )


def _ignite_column(state, x: int) -> None:
    for y in (4, 5):
        _ignite(state, Pos(x, y))
