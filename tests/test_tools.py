"""Tests for the in-process tool layer."""

from __future__ import annotations

import pytest

from silicon_pantheon.server.engine.scenarios import load_scenario
from silicon_pantheon.server.engine.state import Team
from silicon_pantheon.server.session import new_session
from silicon_pantheon.server.tools import TOOL_REGISTRY, ToolError, call_tool


def _session():
    return new_session(load_scenario("01_tiny_skirmish"))


def test_get_state_returns_dict_with_expected_keys():
    s = _session()
    out = call_tool(s, Team.BLUE, "get_state", {})
    assert out["active_player"] == "blue"
    assert out["you"] == "blue"
    assert "board" in out and "units" in out


def test_not_your_turn_blocks_writes():
    s = _session()
    # Red tries to move during blue's turn
    with pytest.raises(ToolError):
        call_tool(s, Team.RED, "move", {"unit_id": "u_r_knight_1", "dest": {"x": 5, "y": 3}})


def test_move_then_attack_end_turn():
    s = _session()
    # Blue knight moves then waits; legal even without attack
    out = call_tool(s, Team.BLUE, "move", {"unit_id": "u_b_knight_1", "dest": {"x": 0, "y": 3}})
    assert out["type"] == "move"
    call_tool(s, Team.BLUE, "wait", {"unit_id": "u_b_knight_1"})
    call_tool(s, Team.BLUE, "wait", {"unit_id": "u_b_archer_1"})
    call_tool(s, Team.BLUE, "end_turn", {})
    assert s.state.active_player is Team.RED


def test_end_turn_blocks_if_unit_moved_but_not_acted():
    s = _session()
    call_tool(s, Team.BLUE, "move", {"unit_id": "u_b_knight_1", "dest": {"x": 0, "y": 3}})
    with pytest.raises(ToolError, match="moved but has not acted"):
        call_tool(s, Team.BLUE, "end_turn", {})


def test_simulate_attack_no_mutation():
    s = _session()
    # Get into attack range first: blue archer is at (1,0), red knight at (5,4) — too far.
    # Just test that simulate doesn't mutate HP by simulating a made-up close match.
    # Use a scenario where attack is in range: blue knight attack red knight not possible
    # but we can simulate between blue archer and red archer (range 5 apart, but we can
    # force from_tile to be in range):
    out = call_tool(
        s,
        Team.BLUE,
        "simulate_attack",
        {
            "attacker_id": "u_b_archer_1",
            "target_id": "u_r_archer_1",
            "from_tile": {"x": 2, "y": 5},
        },
    )
    # Prediction shape is clearly marked so the agent can't confuse
    # simulate_attack's return with an executed attack.
    assert out["kind"] == "prediction"
    assert out["predicted_damage_to_defender"] > 0
    # HP unchanged after simulate
    assert s.state.units["u_r_archer_1"].hp == s.state.units["u_r_archer_1"].stats.hp_max


def test_coach_message_queue():
    s = _session()
    call_tool(s, Team.BLUE, "send_to_agent", {"team": "blue", "text": "push the knight"})
    out = call_tool(s, Team.BLUE, "get_coach_messages", {})
    assert len(out["messages"]) == 1
    assert out["messages"][0]["text"] == "push the knight"
    # Queue drained on read
    out2 = call_tool(s, Team.BLUE, "get_coach_messages", {})
    assert out2["messages"] == []


def test_registry_has_all_tools():
    expected = {
        "get_state",
        "get_unit",
        "get_legal_actions",
        "simulate_attack",
        "get_threat_map",
        "get_history",
        "get_coach_messages",
        "move",
        "attack",
        "heal",
        "wait",
        "end_turn",
        "send_to_agent",
    }
    assert expected == set(TOOL_REGISTRY.keys())
