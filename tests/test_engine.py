"""Engine tests: combat math, movement, win conditions, scenario loading."""

from __future__ import annotations

import pytest

from silicon_pantheon.server.engine.board import reachable_tiles
from silicon_pantheon.server.engine.combat import damage_per_hit, doubles, predict_attack
from silicon_pantheon.server.engine.rules import (
    AttackAction,
    EndTurnAction,
    HealAction,
    IllegalAction,
    MoveAction,
    WaitAction,
    apply,
    legal_actions_for_unit,
)
from silicon_pantheon.server.engine.scenarios import load_scenario
from silicon_pantheon.server.engine.serialize import state_to_dict
from silicon_pantheon.server.engine.state import (
    Board,
    GameState,
    GameStatus,
    Pos,
    Team,
    TerrainType,
    Tile,
    Unit,
    UnitClass,
    UnitStatus,
)
from silicon_pantheon.server.engine.units import make_stats

# ---- helpers ----


def _mk_unit(uid: str, cls: UnitClass, owner: Team, pos: Pos) -> Unit:
    stats = make_stats(cls)
    return Unit(
        id=uid,
        owner=owner,
        class_=cls,
        pos=pos,
        hp=stats.hp_max,
        status=UnitStatus.READY,
        stats=stats,
    )


def _mk_state(
    units: list[Unit],
    *,
    w: int = 8,
    h: int = 8,
    tiles: dict[Pos, Tile] | None = None,
    active: Team = Team.BLUE,
) -> GameState:
    board = Board(width=w, height=h, tiles=tiles or {})
    return GameState(
        game_id="test",
        turn=1,
        max_turns=20,
        active_player=active,
        first_player=active,
        board=board,
        units={u.id: u for u in units},
    )


# ---- combat math ----


def test_damage_physical_basic():
    k = _mk_unit("k", UnitClass.KNIGHT, Team.BLUE, Pos(0, 0))
    a = _mk_unit("a", UnitClass.ARCHER, Team.RED, Pos(1, 0))
    plain = Tile(pos=Pos(1, 0), type=TerrainType.PLAIN)
    # knight atk 8 vs archer def 3 -> 5
    assert damage_per_hit(k, a, plain) == 5


def test_damage_magic_uses_res():
    m = _mk_unit("m", UnitClass.MAGE, Team.BLUE, Pos(0, 0))
    k = _mk_unit("k", UnitClass.KNIGHT, Team.RED, Pos(1, 0))
    plain = Tile(pos=Pos(1, 0), type=TerrainType.PLAIN)
    # mage atk 8 vs knight RES 2 -> 6 (ignores DEF 7)
    assert damage_per_hit(m, k, plain) == 6


def test_damage_minimum_one():
    k = _mk_unit("k", UnitClass.KNIGHT, Team.BLUE, Pos(0, 0))
    k2 = _mk_unit("k2", UnitClass.KNIGHT, Team.RED, Pos(1, 0))
    # DEF 7 + fort DEF bonus 3 = 10 >= atk 8, but damage floored at 1
    fort = Tile(pos=Pos(1, 0), type=TerrainType.FORT, fort_owner=Team.RED)
    assert damage_per_hit(k, k2, fort) == 1


def test_terrain_def_bonus():
    k = _mk_unit("k", UnitClass.KNIGHT, Team.BLUE, Pos(0, 0))
    a = _mk_unit("a", UnitClass.ARCHER, Team.RED, Pos(1, 0))
    forest = Tile(pos=Pos(1, 0), type=TerrainType.FOREST)
    # 8 - (3 + 2) = 3
    assert damage_per_hit(k, a, forest) == 3


def test_doubling_rule():
    cav = _mk_unit("c", UnitClass.CAVALRY, Team.BLUE, Pos(0, 0))
    kn = _mk_unit("k", UnitClass.KNIGHT, Team.RED, Pos(1, 0))
    # cav spd 7 vs knight spd 3; diff 4 >= 3 -> doubles
    assert doubles(cav, kn) is True
    assert doubles(kn, cav) is False


def test_archer_cannot_counter_adjacent():
    a = _mk_unit("a", UnitClass.ARCHER, Team.BLUE, Pos(0, 0))
    k = _mk_unit("k", UnitClass.KNIGHT, Team.RED, Pos(1, 0))
    pred = predict_attack(
        k,
        a,
        attacker_tile=Tile(Pos(1, 0), TerrainType.PLAIN),
        defender_tile=Tile(Pos(0, 0), TerrainType.PLAIN),
    )
    # knight attacks archer at range 1; archer's rng_min=2, cannot counter
    assert pred.will_counter is False


def test_knight_cannot_counter_archer_at_range():
    a = _mk_unit("a", UnitClass.ARCHER, Team.BLUE, Pos(3, 0))
    k = _mk_unit("k", UnitClass.KNIGHT, Team.RED, Pos(0, 0))
    # archer shoots knight from range 3; knight rng 1, cannot counter
    pred = predict_attack(
        a,
        k,
        attacker_tile=Tile(Pos(3, 0), TerrainType.PLAIN),
        defender_tile=Tile(Pos(0, 0), TerrainType.PLAIN),
    )
    assert pred.will_counter is False


# ---- movement ----


def test_reachable_basic():
    k = _mk_unit("k", UnitClass.KNIGHT, Team.BLUE, Pos(3, 3))
    s = _mk_state([k])
    reach = reachable_tiles(s, k)
    # Knight move=3; should reach up to 3 tiles away in Manhattan terms
    assert Pos(3, 3) in reach
    assert Pos(3, 0) in reach  # 3 north
    assert Pos(3, 7) not in reach  # 4 south -> out of range


def test_cavalry_cannot_enter_forest():
    c = _mk_unit("c", UnitClass.CAVALRY, Team.BLUE, Pos(0, 0))
    forest = Tile(pos=Pos(1, 0), type=TerrainType.FOREST)
    s = _mk_state([c], tiles={Pos(1, 0): forest})
    reach = reachable_tiles(s, c)
    assert Pos(1, 0) not in reach


def test_forest_costs_2_for_others():
    kn = _mk_unit("kn", UnitClass.KNIGHT, Team.BLUE, Pos(0, 0))
    forest = Tile(pos=Pos(1, 0), type=TerrainType.FOREST)
    s = _mk_state([kn], tiles={Pos(1, 0): forest})
    reach = reachable_tiles(s, kn)
    # Knight move=3: plain->forest (cost 2) = 2, then one more plain step = 3
    assert reach[Pos(1, 0)] == 2
    assert Pos(2, 0) in reach  # 2 forest + 1 plain = 3


def test_cannot_end_on_occupied_tile():
    k1 = _mk_unit("k1", UnitClass.KNIGHT, Team.BLUE, Pos(0, 0))
    k2 = _mk_unit("k2", UnitClass.KNIGHT, Team.BLUE, Pos(1, 0))
    s = _mk_state([k1, k2])
    reach = reachable_tiles(s, k1)
    assert Pos(1, 0) not in reach  # ally blocks end


def test_cannot_pass_through_enemy():
    k = _mk_unit("k", UnitClass.KNIGHT, Team.BLUE, Pos(0, 0))
    e = _mk_unit("e", UnitClass.KNIGHT, Team.RED, Pos(1, 0))
    s = _mk_state([k, e])
    reach = reachable_tiles(s, k)
    # Enemy at (1,0) blocks; (2,0) should be unreachable via that path
    # but reachable via (0,1)->(1,1)->(2,1)? no, that's different column
    # Simpler check: we can still reach tiles not behind the enemy
    assert Pos(0, 1) in reach
    # And we cannot end on the enemy tile
    assert Pos(1, 0) not in reach


# ---- apply actions ----


def test_apply_move_then_attack():
    k = _mk_unit("k", UnitClass.KNIGHT, Team.BLUE, Pos(0, 0))
    a = _mk_unit("a", UnitClass.ARCHER, Team.RED, Pos(3, 0))
    s = _mk_state([k, a])
    apply(s, MoveAction(unit_id="k", dest=Pos(2, 0)))
    assert k.status is UnitStatus.MOVED
    assert k.pos == Pos(2, 0)
    apply(s, AttackAction(unit_id="k", target_id="a"))
    assert k.status is UnitStatus.DONE
    # knight hits archer once for 8-3=5; archer (dead? 18-5=13)
    assert a.hp == 13


def test_apply_move_twice_fails():
    k = _mk_unit("k", UnitClass.KNIGHT, Team.BLUE, Pos(0, 0))
    s = _mk_state([k])
    apply(s, MoveAction(unit_id="k", dest=Pos(1, 0)))
    with pytest.raises(IllegalAction):
        apply(s, MoveAction(unit_id="k", dest=Pos(2, 0)))


def test_apply_attack_out_of_range():
    k = _mk_unit("k", UnitClass.KNIGHT, Team.BLUE, Pos(0, 0))
    a = _mk_unit("a", UnitClass.ARCHER, Team.RED, Pos(5, 0))
    s = _mk_state([k, a])
    with pytest.raises(IllegalAction):
        apply(s, AttackAction(unit_id="k", target_id="a"))


def test_heal_restores_hp():
    m = _mk_unit("m", UnitClass.MAGE, Team.BLUE, Pos(0, 0))
    ally = _mk_unit("k", UnitClass.KNIGHT, Team.BLUE, Pos(1, 0))
    ally.hp = 10
    s = _mk_state([m, ally])
    apply(s, HealAction(healer_id="m", target_id="k"))
    assert ally.hp == 18  # 10 + 8
    assert m.status is UnitStatus.DONE


def test_heal_self_fails():
    m = _mk_unit("m", UnitClass.MAGE, Team.BLUE, Pos(0, 0))
    m.hp = 5
    s = _mk_state([m])
    with pytest.raises(IllegalAction):
        apply(s, HealAction(healer_id="m", target_id="m"))


# ---- turn flow ----


def test_end_turn_swaps_active_and_resets_status():
    k = _mk_unit("k", UnitClass.KNIGHT, Team.BLUE, Pos(0, 0))
    r = _mk_unit("r", UnitClass.KNIGHT, Team.RED, Pos(5, 5))
    s = _mk_state([k, r])
    apply(s, MoveAction(unit_id="k", dest=Pos(1, 0)))
    apply(s, WaitAction(unit_id="k"))  # status -> DONE
    apply(s, EndTurnAction())
    assert s.active_player is Team.RED
    # Red's units should be READY
    assert r.status is UnitStatus.READY
    # Still turn 1 (first_player was blue; active=red; hasn't wrapped)
    assert s.turn == 1


def test_full_turn_cycle_increments_turn():
    k = _mk_unit("k", UnitClass.KNIGHT, Team.BLUE, Pos(0, 0))
    r = _mk_unit("r", UnitClass.KNIGHT, Team.RED, Pos(5, 5))
    s = _mk_state([k, r])
    apply(s, EndTurnAction())
    apply(s, EndTurnAction())
    assert s.turn == 2
    assert s.active_player is Team.BLUE


def test_elimination_win():
    k = _mk_unit("k", UnitClass.KNIGHT, Team.BLUE, Pos(0, 0))
    r = _mk_unit("r", UnitClass.ARCHER, Team.RED, Pos(1, 0))
    r.hp = 1  # one-shot
    s = _mk_state([k, r])
    apply(s, AttackAction(unit_id="k", target_id="r"))
    apply(s, EndTurnAction())
    assert s.status is GameStatus.GAME_OVER
    assert s.winner is Team.BLUE


def test_fort_seize_win():
    # blue knight standing on red's fort at end of turn -> blue wins
    k = _mk_unit("k", UnitClass.KNIGHT, Team.BLUE, Pos(5, 5))
    r = _mk_unit("r", UnitClass.KNIGHT, Team.RED, Pos(0, 0))
    red_fort = Tile(pos=Pos(5, 5), type=TerrainType.FORT, fort_owner=Team.RED)
    s = _mk_state([k, r], tiles={Pos(5, 5): red_fort})
    apply(s, EndTurnAction())
    assert s.status is GameStatus.GAME_OVER
    assert s.winner is Team.BLUE


def test_max_turns_draw():
    k = _mk_unit("k", UnitClass.KNIGHT, Team.BLUE, Pos(0, 0))
    r = _mk_unit("r", UnitClass.KNIGHT, Team.RED, Pos(5, 5))
    s = _mk_state([k, r])
    s.max_turns = 2
    # blue pass, red pass -> turn 2
    apply(s, EndTurnAction())
    apply(s, EndTurnAction())
    assert s.turn == 2
    # blue pass, red pass -> turn 3, exceeds max
    apply(s, EndTurnAction())
    apply(s, EndTurnAction())
    assert s.status is GameStatus.GAME_OVER
    assert s.winner is None


def test_fort_heal_on_turn_start():
    k = _mk_unit("k", UnitClass.KNIGHT, Team.BLUE, Pos(0, 0))
    k.hp = 10
    fort = Tile(pos=Pos(0, 0), type=TerrainType.FORT, fort_owner=Team.BLUE)
    r = _mk_unit("r", UnitClass.KNIGHT, Team.RED, Pos(5, 5))
    s = _mk_state([k, r], tiles={Pos(0, 0): fort})
    # Blue ends turn -> red's turn -> red ends turn -> blue's turn (heal fires)
    apply(s, EndTurnAction())
    apply(s, EndTurnAction())
    assert k.hp == 13


# ---- legal_actions ----


def test_legal_actions_ready_unit():
    k = _mk_unit("k", UnitClass.KNIGHT, Team.BLUE, Pos(0, 0))
    e = _mk_unit("e", UnitClass.ARCHER, Team.RED, Pos(3, 0))
    s = _mk_state([k, e])
    la = legal_actions_for_unit(s, "k")
    assert la["status"] == "ready"
    assert la["can_wait"] is True
    assert len(la["moves"]) > 0
    # After moving to (2, 0), knight could attack archer — should be in attacks list
    attack_targets = {(a["target_id"], a["from"]["x"], a["from"]["y"]) for a in la["attacks"]}
    assert ("e", 2, 0) in attack_targets


# ---- scenarios + serialize ----


def test_load_tiny_skirmish():
    s = load_scenario("01_tiny_skirmish")
    assert s.board.width == 6
    assert s.board.height == 6
    assert len(s.units_of(Team.BLUE)) == 2
    assert len(s.units_of(Team.RED)) == 2


def test_state_to_dict_roundtrip():
    s = load_scenario("01_tiny_skirmish")
    d = state_to_dict(s, viewer=Team.BLUE)
    assert d["active_player"] == "blue"
    assert d["you"] == "blue"
    assert d["board"]["width"] == 6
    assert any(f["owner"] == "blue" for f in d["board"]["forts"])
