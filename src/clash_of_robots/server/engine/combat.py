"""Damage resolution: attack formula, counter-attack, doubling rule."""

from __future__ import annotations

from dataclasses import dataclass

from .board import in_attack_range
from .state import Pos, Tile, Unit


@dataclass
class AttackPrediction:
    damage_per_hit: int  # damage the attacker deals per hit
    attacker_hits: int  # 1 or 2 (doubling)
    total_damage_to_defender: int  # damage_per_hit * attacker_hits, capped at defender.hp
    defender_dies: bool
    will_counter: bool
    counter_damage_per_hit: int  # 0 if no counter
    counter_hits: int  # 0, 1, or 2
    total_counter_damage: int
    attacker_dies: bool  # after resolving both attacker swings and counter


def damage_per_hit(attacker: Unit, defender: Unit, defender_tile: Tile) -> int:
    """max(1, atk - defense-or-res) with terrain bonus applied to the defender."""
    if attacker.stats.is_magic:
        mitigation = defender.stats.res + defender_tile.res_bonus()
    else:
        mitigation = defender.stats.defense + defender_tile.def_bonus()
    return max(1, attacker.stats.atk - mitigation)


def doubles(attacker: Unit, defender: Unit) -> bool:
    return attacker.stats.spd >= defender.stats.spd + 3


def predict_attack(
    attacker: Unit,
    defender: Unit,
    attacker_tile: Tile,
    defender_tile: Tile,
    attacker_pos: Pos | None = None,
) -> AttackPrediction:
    """Predict outcome of an attack without mutating any unit.

    `attacker_pos` defaults to attacker.pos; callers can override to simulate
    attacks from a hypothetical post-move position.
    """
    if attacker_pos is None:
        attacker_pos = attacker.pos

    # Attacker hits (doubles if fast enough)
    per_hit = damage_per_hit(attacker, defender, defender_tile)
    atk_hits = 2 if doubles(attacker, defender) else 1
    defender_hp_after = max(0, defender.hp - per_hit * atk_hits)
    total_to_defender = defender.hp - defender_hp_after
    defender_dies = defender_hp_after == 0

    # Counter: defender counters iff attacker's position is within the
    # defender's attack range (we treat the counter as happening after the
    # attacker's full salvo, consistent with FE-style combat).
    will_counter = (not defender_dies) and in_attack_range(
        defender.pos, attacker_pos, defender.stats
    )
    counter_per_hit = 0
    counter_hits = 0
    total_counter = 0
    attacker_dies = False
    if will_counter:
        counter_per_hit = damage_per_hit(defender, attacker, attacker_tile)
        counter_hits = 2 if doubles(defender, attacker) else 1
        attacker_hp_after = max(0, attacker.hp - counter_per_hit * counter_hits)
        total_counter = attacker.hp - attacker_hp_after
        attacker_dies = attacker_hp_after == 0

    return AttackPrediction(
        damage_per_hit=per_hit,
        attacker_hits=atk_hits,
        total_damage_to_defender=total_to_defender,
        defender_dies=defender_dies,
        will_counter=will_counter,
        counter_damage_per_hit=counter_per_hit,
        counter_hits=counter_hits,
        total_counter_damage=total_counter,
        attacker_dies=attacker_dies,
    )
