"""Post-game statistics computed from the action history and agent telemetry.

The TUI accumulates agent-side metrics (thinking time, token usage,
tool calls) during gameplay and combines them with server-side action
history at match end to produce a unified stats snapshot displayed
on the post-match screen.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class UnitKillStats:
    """Per-unit combat record."""
    unit_id: str
    display_name: str
    owner: str  # "blue" | "red"
    kills: int = 0
    damage_dealt: int = 0
    damage_taken: int = 0
    healing_done: int = 0
    alive: bool = True


@dataclass
class TeamStats:
    """Per-team aggregate stats."""
    team: str
    units_fielded: int = 0
    units_lost: int = 0
    total_damage_dealt: int = 0
    total_damage_taken: int = 0
    total_healing: int = 0
    total_moves: int = 0
    tiles_moved: int = 0
    turns_played: int = 0
    # Agent telemetry (only for the local player's team).
    total_thinking_time_s: float = 0.0
    total_tokens: int = 0
    total_tool_calls: int = 0
    total_errors: int = 0


@dataclass
class MatchStats:
    """Full post-game statistics."""
    blue: TeamStats = field(default_factory=lambda: TeamStats(team="blue"))
    red: TeamStats = field(default_factory=lambda: TeamStats(team="red"))
    units: dict[str, UnitKillStats] = field(default_factory=dict)
    turns_total: int = 0
    first_kill_turn: int | None = None
    winner: str | None = None
    reason: str = ""

    def team(self, name: str) -> TeamStats:
        return self.blue if name == "blue" else self.red

    def mvp(self) -> UnitKillStats | None:
        """Unit with the most kills, tiebroken by damage dealt."""
        candidates = [u for u in self.units.values() if u.kills > 0]
        if not candidates:
            candidates = [u for u in self.units.values() if u.damage_dealt > 0]
        if not candidates:
            return None
        return max(candidates, key=lambda u: (u.kills, u.damage_dealt))


def compute_match_stats(
    history: list[dict[str, Any]],
    units: list[dict[str, Any]],
    game_state: dict[str, Any] | None = None,
    scenario_description: dict[str, Any] | None = None,
) -> MatchStats:
    """Build MatchStats from the action history and final unit list.

    ``history`` is the full action log from ``get_history(last_n=0)``.
    ``units`` is the final ``get_state().units`` list.
    ``game_state`` is the final game state dict (for winner/turns).
    ``scenario_description`` provides display names for units.
    """
    stats = MatchStats()
    gs = game_state or {}
    stats.turns_total = gs.get("turn", 0)
    stats.winner = gs.get("winner")
    stats.reason = (gs.get("last_action") or {}).get("reason", "")
    unit_classes = (scenario_description or {}).get("unit_classes") or {}

    # Initialize unit records from the final unit list.
    for u in units:
        uid = u.get("id", "")
        owner = u.get("owner", "?")
        cls = u.get("class", "")
        spec = unit_classes.get(cls) or {}
        display = (
            u.get("display_name")
            or spec.get("display_name")
            or cls
            or uid
        )
        stats.units[uid] = UnitKillStats(
            unit_id=uid,
            display_name=display,
            owner=owner,
            alive=u.get("alive", u.get("hp", 0) > 0),
        )
        ts = stats.team(owner)
        ts.units_fielded += 1
        if not stats.units[uid].alive:
            ts.units_lost += 1

    current_turn = 0
    for action in history:
        atype = action.get("type")
        uid = action.get("unit_id") or action.get("healer_id", "")
        owner = _owner_of(uid, stats.units)

        if atype == "end_turn":
            current_turn += 1
            if owner:
                stats.team(owner).turns_played += 1
            continue

        if atype == "move":
            if owner:
                stats.team(owner).total_moves += 1
            continue

        if atype == "attack":
            dmg = action.get("damage_dealt", 0)
            counter = action.get("counter_damage", 0)
            target_id = action.get("target_id", "")
            target_owner = _owner_of(target_id, stats.units)

            if uid in stats.units:
                stats.units[uid].damage_dealt += dmg
            if target_id in stats.units:
                stats.units[target_id].damage_taken += dmg
            if uid in stats.units:
                stats.units[uid].damage_taken += counter

            if owner:
                stats.team(owner).total_damage_dealt += dmg
                stats.team(owner).total_damage_taken += counter
            if target_owner:
                stats.team(target_owner).total_damage_dealt += counter
                stats.team(target_owner).total_damage_taken += dmg

            if action.get("target_killed") and uid in stats.units:
                stats.units[uid].kills += 1
                if stats.first_kill_turn is None:
                    stats.first_kill_turn = current_turn
            if action.get("attacker_killed") and target_id in stats.units:
                stats.units[target_id].kills += 1
                if stats.first_kill_turn is None:
                    stats.first_kill_turn = current_turn
            continue

        if atype == "heal":
            amt = action.get("heal_amount", action.get("healed", 0))
            if uid in stats.units:
                stats.units[uid].healing_done += amt
            if owner:
                stats.team(owner).total_healing += amt
            continue

    return stats


def _owner_of(uid: str, units: dict[str, UnitKillStats]) -> str:
    """Look up which team owns a unit, falling back to ID convention."""
    if uid in units:
        return units[uid].owner
    # Convention: u_b_class_n = blue, u_r_class_n = red.
    parts = uid.split("_")
    if len(parts) >= 2:
        if parts[1] == "b":
            return "blue"
        if parts[1] == "r":
            return "red"
    return ""
