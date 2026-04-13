"""Smoke tests for the replay viewer: parses every event kind we emit."""

from __future__ import annotations

import json
from pathlib import Path

from clash_of_robots.match.replay_viewer import _fmt_event, _iter_events, view_replay


def _write_replay(tmp_path: Path, events: list[dict]) -> Path:
    path = tmp_path / "replay.jsonl"
    with path.open("w", encoding="utf-8") as f:
        for ev in events:
            f.write(json.dumps(ev) + "\n")
    return path


def test_fmt_event_covers_known_kinds() -> None:
    cases = [
        {
            "kind": "agent_thought",
            "turn": 1,
            "payload": {"team": "blue", "text": "push the right flank"},
        },
        {
            "kind": "action",
            "turn": 1,
            "payload": {
                "type": "move",
                "unit_id": "u_b_archer_1",
                "from": {"x": 0, "y": 0},
                "to": {"x": 1, "y": 1},
            },
        },
        {
            "kind": "action",
            "turn": 1,
            "payload": {
                "type": "attack",
                "unit_id": "u_b_knight_1",
                "target_id": "u_r_archer_1",
                "damage_to_defender": 6,
                "counter_damage": 0,
                "by": "blue",
            },
        },
        {
            "kind": "action",
            "turn": 2,
            "payload": {
                "type": "end_turn",
                "by": "red",
                "winner": "red",
                "reason": "seize",
                "seized_at": {"x": 0, "y": 0},
            },
        },
        {"kind": "coach_message", "turn": 1, "payload": {"to": "blue", "text": "hold"}},
        {"kind": "agent_error", "turn": 1, "payload": {"team": "red", "error": "boom"}},
        {"kind": "forced_end_turn", "turn": 1, "payload": {"team": "blue"}},
    ]
    for ev in cases:
        text = _fmt_event(ev)
        rendered = text.plain
        assert rendered.startswith("T"), rendered
        assert "?" not in rendered or ev["kind"] == "agent_error"


def test_iter_events_skips_blank_and_malformed(tmp_path: Path) -> None:
    path = tmp_path / "replay.jsonl"
    path.write_text(
        json.dumps({"kind": "agent_thought", "turn": 1, "payload": {"team": "blue", "text": "x"}})
        + "\n\nnot json\n"
        + json.dumps({"kind": "action", "turn": 1, "payload": {"type": "wait", "unit_id": "u"}})
        + "\n",
        encoding="utf-8",
    )
    events = list(_iter_events(path))
    kinds = [e["kind"] for e in events]
    # Blank lines skipped; bad line surfaced as "malformed" so the viewer shows it.
    assert kinds == ["agent_thought", "malformed", "action"]


def test_view_replay_no_pager_returns_zero(tmp_path: Path, capsys) -> None:
    path = _write_replay(
        tmp_path,
        [
            {
                "kind": "agent_thought",
                "turn": 1,
                "payload": {"team": "blue", "text": "hi"},
            }
        ],
    )
    rc = view_replay(path, use_pager=False)
    assert rc == 0


def test_view_replay_missing_file_returns_nonzero(tmp_path: Path) -> None:
    rc = view_replay(tmp_path / "nope.jsonl", use_pager=False)
    assert rc != 0
