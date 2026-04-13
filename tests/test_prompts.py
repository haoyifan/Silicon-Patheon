"""Tests for the system-prompt builder, focused on lesson injection."""

from __future__ import annotations

from clash_of_odin.harness.prompts import build_system_prompt
from clash_of_odin.lessons import Lesson
from clash_of_odin.server.engine.state import Team


def _lesson(slug: str, title: str, body: str, team: str = "blue") -> Lesson:
    return Lesson(
        slug=slug,
        title=title,
        scenario="01_tiny_skirmish",
        team=team,
        model="m",
        outcome="loss",
        reason="seize",
        created_at="2026-04-12T14:30:00+00:00",
        body=body,
    )


def test_no_lessons_means_no_lessons_section() -> None:
    out = build_system_prompt(Team.BLUE, max_turns=20, strategy=None, lessons=None)
    assert "Prior lessons" not in out
    # And passing an empty list is equivalent.
    out2 = build_system_prompt(Team.BLUE, max_turns=20, strategy=None, lessons=[])
    assert "Prior lessons" not in out2


def test_lessons_are_embedded_with_title_and_body() -> None:
    lessons = [
        _lesson("a", "Guard the fort", "Always keep a unit one step from your home fort."),
        _lesson("b", "Bait with Archer", "Archers can draw cavalry into forest traps.", team="red"),
    ]
    out = build_system_prompt(Team.BLUE, max_turns=20, strategy=None, lessons=lessons)
    assert "Prior lessons from this scenario" in out
    assert "Guard the fort" in out
    assert "Always keep a unit one step from your home fort." in out
    assert "Bait with Archer" in out
    # Team/outcome tag present
    assert "[blue loss]" in out
    assert "[red loss]" in out


def test_lessons_dont_suppress_strategy() -> None:
    out = build_system_prompt(
        Team.BLUE,
        max_turns=20,
        strategy="rush the right flank",
        lessons=[_lesson("a", "T", "B")],
    )
    assert "rush the right flank" in out
    assert "Prior lessons from this scenario" in out
