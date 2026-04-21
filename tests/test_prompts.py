"""Tests for the system-prompt builder, focused on lesson injection."""

from __future__ import annotations

from silicon_pantheon.harness.prompts import build_system_prompt
from silicon_pantheon.lessons import Lesson
from silicon_pantheon.server.engine.state import Team


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


def test_prompt_reflects_scenario_fog_mode() -> None:
    """Regression: the prompt's fog section must reflect the scenario
    bundle's declared fog_of_war. On 08_kadesh the scenario ships with
    rules.fog_of_war=false (legacy boolean coerced to "none") but the
    worker created the room with classic fog — the agent's prompt
    then said fog=none while the server ran classic, and the agent
    reported "战争迷雾意外激活". The fix pushes the session's effective
    fog into the bundle's rules before building the prompt; this test
    asserts the builder honours whatever rules value it gets."""
    bundle_classic = {
        "name": "t",
        "description": "t",
        "rules": {"fog_of_war": "classic"},
    }
    bundle_none = {
        "name": "t",
        "description": "t",
        "rules": {"fog_of_war": "none"},
    }
    out_classic = build_system_prompt(
        Team.BLUE, max_turns=20, strategy=None, lessons=None,
        scenario_description=bundle_classic,
    )
    out_none = build_system_prompt(
        Team.BLUE, max_turns=20, strategy=None, lessons=None,
        scenario_description=bundle_none,
    )
    # The two modes have different fog rules blocks — exact copy
    # is in harness.prompts but we just look for distinctive
    # phrasing from each.
    assert out_classic != out_none
    # Classic-fog block mentions that units in fog drop out of
    # the state; none-fog block says full visibility.
    assert (
        "classic" in out_classic.lower()
        or "fog" in out_classic.lower()
    )
