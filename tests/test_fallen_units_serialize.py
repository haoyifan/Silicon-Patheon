"""Regression: dead units stay visible in state.units payload.

Before this fix, killing a unit removed it from `state.units` AND
from the serialized `units` list — so the TUI's Player-roster panel
silently lost rows as units died. The fix keeps a parallel
`state.fallen_units` dict whose snapshots get appended to the
serialized payload with `alive=False`, so clients can still render
them (dim + ✗ dead-marker) while the engine's live-unit invariants
stay untouched."""

from __future__ import annotations

from silicon_pantheon.server.engine.rules import (
    AttackAction,
    MoveAction,
    apply,
)
from silicon_pantheon.server.engine.scenarios import build_state
from silicon_pantheon.server.engine.serialize import state_to_dict
from silicon_pantheon.server.engine.state import Pos


def _lethal_cfg() -> dict:
    """Two adjacent knights (melee range = 1)."""
    return {
        "board": {"width": 3, "height": 3, "terrain": [], "forts": []},
        "armies": {
            "blue": [{"class": "knight", "pos": {"x": 0, "y": 0}}],
            "red":  [{"class": "knight", "pos": {"x": 1, "y": 0}}],
        },
        "rules": {"max_turns": 10, "first_player": "blue"},
    }


def test_killed_unit_remains_in_serialized_units_with_alive_false():
    state = build_state(_lethal_cfg())
    blue_id = next(iter(u.id for u in state.units.values() if u.owner.value == "blue"))
    red_id = next(iter(u.id for u in state.units.values() if u.owner.value == "red"))

    # Bypass balance math: drop red to 1 HP and land one attack to
    # drive it through the death path. We're testing the serializer,
    # not combat resolution.
    state.units[red_id].hp = 1
    apply(state, AttackAction(unit_id=blue_id, target_id=red_id))

    assert red_id not in state.units, "red should have died"
    assert red_id in state.fallen_units, "fallen snapshot must be captured"

    # Serialize and verify the dead unit is still present with alive=False.
    payload = state_to_dict(state)
    unit_rows = {u["id"]: u for u in payload["units"]}
    assert red_id in unit_rows, (
        "dead unit disappeared from serialized units — the Player "
        "roster panel will silently lose this row"
    )
    assert unit_rows[red_id]["alive"] is False
    assert unit_rows[red_id]["hp"] == 0
    # Position is preserved so a future "show corpses" map overlay
    # would have something to anchor on.
    assert "pos" in unit_rows[red_id]
