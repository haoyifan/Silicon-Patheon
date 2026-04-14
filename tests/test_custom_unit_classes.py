"""Tests for scenario unit_classes: block — custom classes and overrides."""

from __future__ import annotations

import pytest

from clash_of_odin.server.engine.scenarios import build_state


def _cfg(*, unit_classes: dict | None = None, blue=None, red=None) -> dict:
    return {
        "schema_version": 1,
        "board": {"width": 4, "height": 4, "terrain": [], "forts": []},
        "unit_classes": unit_classes or {},
        "armies": {
            "blue": blue or [{"class": "knight", "pos": {"x": 0, "y": 0}}],
            "red": red or [{"class": "knight", "pos": {"x": 3, "y": 3}}],
        },
        "rules": {"max_turns": 10, "first_player": "blue"},
    }


def test_custom_class_can_be_used_in_army() -> None:
    state = build_state(
        _cfg(
            unit_classes={
                "monkey_king": {
                    "hp_max": 45,
                    "atk": 16,
                    "defense": 5,
                    "spd": 11,
                    "move": 8,
                    "sight": 6,
                    "tags": ["flying", "divine"],
                    "mp_max": 40,
                    "abilities": ["seventy_two_transformations"],
                }
            },
            blue=[{"class": "monkey_king", "pos": {"x": 0, "y": 0}}],
        )
    )
    [uid] = [u for u in state.units if u.startswith("u_b_")]
    u = state.units[uid]
    assert u.class_ == "monkey_king"
    assert u.stats.hp_max == 45
    assert u.stats.tags == ["flying", "divine"]
    assert u.stats.mp_max == 40
    assert u.stats.abilities == ["seventy_two_transformations"]


def test_custom_class_can_override_builtin() -> None:
    state = build_state(
        _cfg(
            unit_classes={"knight": {"hp_max": 999, "atk": 0, "defense": 0}},
        )
    )
    knight = state.units["u_b_knight_1"]
    assert knight.stats.hp_max == 999


def test_unknown_class_raises() -> None:
    with pytest.raises(ValueError) as excinfo:
        build_state(
            _cfg(
                unit_classes={},
                blue=[{"class": "nonexistent", "pos": {"x": 0, "y": 0}}],
            )
        )
    assert "unknown unit class" in str(excinfo.value)


def test_reserved_fields_default_to_empty() -> None:
    state = build_state(
        _cfg(
            unit_classes={"bare": {"hp_max": 10, "atk": 3}},
            blue=[{"class": "bare", "pos": {"x": 0, "y": 0}}],
        )
    )
    u = state.units["u_b_bare_1"]
    assert u.stats.tags == []
    assert u.stats.mp_max == 0
    assert u.stats.abilities == []
    assert u.stats.default_inventory == []
    assert u.stats.damage_profile == {}
    assert u.stats.defense_profile == {}
    assert u.stats.bonus_vs_tags == []
    assert u.stats.vulnerability_to_tags == []


def test_custom_class_stats_are_independent_across_units() -> None:
    """Two units of the same custom class shouldn't share a stats dict."""
    state = build_state(
        _cfg(
            unit_classes={"twin": {"hp_max": 20, "tags": ["wanderer"]}},
            blue=[
                {"class": "twin", "pos": {"x": 0, "y": 0}},
                {"class": "twin", "pos": {"x": 1, "y": 0}},
            ],
        )
    )
    a = state.units["u_b_twin_1"]
    b = state.units["u_b_twin_2"]
    assert a.stats is not b.stats
    a.stats.tags.append("mutated")
    assert "mutated" not in b.stats.tags
