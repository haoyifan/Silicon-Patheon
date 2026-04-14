"""Agent prompt content — scenario context in the system prompt,
slim per-unit fields in the per-turn + tool responses."""

from __future__ import annotations

from clash_of_odin.harness.prompts import (
    build_system_prompt,
    build_turn_prompt_from_state_dict,
    _slim_unit,
)
from clash_of_odin.server.engine.state import Team


def _fake_bundle() -> dict:
    return {
        "name": "Test Map",
        "description": "a little test map.",
        "armies": {
            "blue": [{"class": "hero", "pos": {"x": 1, "y": 1}}],
            "red": [{"class": "boss", "pos": {"x": 8, "y": 8}}],
        },
        "unit_classes": {
            "hero": {"display_name": "The Hero",
                     "description": "Test hero.",
                     "hp_max": 30, "atk": 10, "defense": 5, "res": 3,
                     "spd": 6, "rng_min": 1, "rng_max": 1, "move": 4,
                     "glyph": "H"},
            "boss": {"display_name": "The Boss",
                     "description": "Test boss.",
                     "hp_max": 40, "atk": 12, "defense": 7, "res": 4,
                     "spd": 5, "rng_min": 1, "rng_max": 1, "move": 3,
                     "glyph": "B"},
        },
        "terrain_types": {
            "plain": {"description": "No modifiers."},
            "swamp": {"move_cost": 2, "heals": -2, "description": "Hurts."},
        },
        "board": {
            "width": 10, "height": 10,
            "terrain": [{"x": 3, "y": 3, "type": "swamp"}],
            "forts": [{"x": 9, "y": 9, "owner": "red"}],
        },
        "win_conditions": [
            {"type": "protect_unit", "unit_id": "u_b_hero_1",
             "owning_team": "blue"},
            {"type": "eliminate_all_enemy_units"},
        ],
    }


def test_system_prompt_carries_scenario_specific_context():
    sp = build_system_prompt(
        team=Team.BLUE, max_turns=30, strategy=None, lessons=None,
        scenario_description=_fake_bundle(),
    )
    # Scenario name and story.
    assert "Test Map" in sp
    assert "a little test map" in sp
    # Classes with display names appear, not generic Knight/Archer.
    assert "The Hero" in sp
    assert "The Boss" in sp
    assert "Knight" not in sp  # old hardcoded Knight/Archer paragraph gone
    # Stats rendered.
    assert "HP 30" in sp and "HP 40" in sp
    # Terrain catalog includes custom types with effect summaries.
    assert "swamp" in sp
    assert "move 2" in sp
    # Win conditions side-explicit.
    assert "Red wins" in sp or "Either side wins" in sp
    # Map grid contains at least one unit glyph at a plausible row.
    assert "H" in sp
    # The describe_class escape hatch is documented.
    assert "describe_class" in sp


def test_system_prompt_survives_empty_scenario_bundle():
    """If describe_scenario failed, the system prompt should still
    render without blowing up — we don't want a prompt error to
    kill the agent session."""
    sp = build_system_prompt(
        team=Team.BLUE, max_turns=20, strategy=None, lessons=None,
        scenario_description=None,
    )
    assert "unknown scenario" in sp or "(no scenario description" in sp


def test_slim_unit_keeps_combat_fields_drops_class_invariants():
    full_unit = {
        "id": "u_b_x_1", "owner": "blue", "class": "x", "pos": {"x": 1, "y": 2},
        "hp": 10, "hp_max": 30, "atk": 8, "def": 5, "res": 3,
        "spd": 6, "move": 4, "rng": [1, 1],
        "status": "ready", "alive": True,
        "is_magic": False, "can_heal": False,
        # Noise that shouldn't reach the agent.
        "display_name": "X", "glyph": "X", "color": "cyan",
        "description": "flavor text", "art_frames": ["frame"],
        "tags": ["hero"], "mp_max": 0, "mp_per_turn": 0,
        "abilities": [], "default_inventory": [],
        "damage_profile": {}, "defense_profile": {},
        "bonus_vs_tags": [], "vulnerability_to_tags": [],
    }
    slim = _slim_unit(full_unit)
    kept = set(slim.keys())
    assert "id" in kept and "hp" in kept and "pos" in kept and "status" in kept
    for junk in ("display_name", "glyph", "color", "description",
                 "art_frames", "tags", "mp_max", "abilities",
                 "damage_profile", "bonus_vs_tags"):
        assert junk not in kept


def test_turn_prompt_only_carries_dynamic_state():
    state_dict = {
        "turn": 3, "active_player": "blue", "you": "blue",
        "board": {"width": 10, "height": 10, "forts": []},
        "units": [
            {"id": "u_b_x_1", "owner": "blue", "class": "x",
             "pos": {"x": 1, "y": 1},
             "hp": 10, "hp_max": 30, "atk": 8, "def": 5, "res": 3,
             "spd": 6, "move": 4, "rng": [1, 1],
             "status": "ready", "alive": True,
             "is_magic": False, "can_heal": False,
             "display_name": "X", "art_frames": ["bloat"],
             "description": "should not appear"},
        ],
        "last_action": None,
    }
    p = build_turn_prompt_from_state_dict(state_dict, Team.BLUE)
    assert "hp" in p
    assert "art_frames" not in p
    assert "should not appear" not in p
