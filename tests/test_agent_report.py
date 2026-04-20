"""Tests for the agent-report tool sinks (jsonl writer + helper)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest


def test_append_agent_report_jsonl_creates_dir_and_file(tmp_path: Path) -> None:
    """Helper writes one line per call to a dated file under ~/.silicon-pantheon/debug-reports."""
    from silicon_pantheon.server.game_tools import _append_agent_report_jsonl

    with patch.object(Path, "home", return_value=tmp_path):
        event = {
            "timestamp": 1710000000.0,  # 2024-03-09 UTC
            "room_id": "room-abc",
            "turn": 3,
            "team": "blue",
            "player": {"display_name": "tester", "provider": "x", "model": "y"},
            "category": "confusion",
            "summary": "enemy vanished",
            "details": None,
        }
        _append_agent_report_jsonl(event)

        out_dir = tmp_path / ".silicon-pantheon" / "debug-reports"
        assert out_dir.is_dir()
        files = list(out_dir.iterdir())
        assert len(files) == 1
        # File name is YYYYMMDD.jsonl — local timezone, so just check extension.
        assert files[0].suffix == ".jsonl"
        content = files[0].read_text(encoding="utf-8").splitlines()
        assert len(content) == 1
        parsed = json.loads(content[0])
        assert parsed["room_id"] == "room-abc"
        assert parsed["summary"] == "enemy vanished"
        assert parsed["category"] == "confusion"


def test_append_agent_report_jsonl_appends(tmp_path: Path) -> None:
    """Repeated calls on the same day land in the same file, one line each."""
    from silicon_pantheon.server.game_tools import _append_agent_report_jsonl

    with patch.object(Path, "home", return_value=tmp_path):
        base = {
            "timestamp": 1710000000.0,
            "room_id": "r",
            "turn": 1,
            "team": "red",
            "player": {},
            "category": "bug",
            "details": None,
        }
        _append_agent_report_jsonl({**base, "summary": "one"})
        _append_agent_report_jsonl({**base, "summary": "two"})
        _append_agent_report_jsonl({**base, "summary": "three"})

        out_dir = tmp_path / ".silicon-pantheon" / "debug-reports"
        files = list(out_dir.iterdir())
        assert len(files) == 1
        lines = files[0].read_text(encoding="utf-8").splitlines()
        assert [json.loads(x)["summary"] for x in lines] == ["one", "two", "three"]


def test_append_agent_report_jsonl_preserves_unicode(tmp_path: Path) -> None:
    """Non-ASCII summaries (e.g. Chinese) round-trip unchanged."""
    from silicon_pantheon.server.game_tools import _append_agent_report_jsonl

    with patch.object(Path, "home", return_value=tmp_path):
        _append_agent_report_jsonl({
            "timestamp": 1710000000.0,
            "room_id": "r",
            "turn": 1,
            "team": "blue",
            "player": {},
            "category": "confusion",
            "summary": "铠之巨人突然消失了",
            "details": None,
        })
        files = list((tmp_path / ".silicon-pantheon" / "debug-reports").iterdir())
        content = files[0].read_text(encoding="utf-8")
        # ensure_ascii=False keeps the Chinese literal in the file for grep.
        assert "铠之巨人突然消失了" in content
