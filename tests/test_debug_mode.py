"""Tests for `silicon_pantheon.shared.debug`.

Debug mode (SILICON_DEBUG=1) must turn every swallowed invariant
violation into a crashing assertion so real bugs surface at the
source site instead of being buried in logs.
"""

from __future__ import annotations

import logging

import pytest

from silicon_pantheon.shared.debug import (
    InvariantViolation,
    invariant,
    is_debug,
    reraise_in_debug,
)


# ---- is_debug() ----

def test_is_debug_defaults_off(monkeypatch):
    monkeypatch.delenv("SILICON_DEBUG", raising=False)
    assert is_debug() is False


def test_is_debug_on_when_env_set(monkeypatch):
    monkeypatch.setenv("SILICON_DEBUG", "1")
    assert is_debug() is True


def test_is_debug_off_on_any_other_value(monkeypatch):
    # Only "1" enables debug — ambiguous values stay off, not on.
    for v in ("0", "", "true", "yes", "on", "false"):
        monkeypatch.setenv("SILICON_DEBUG", v)
        assert is_debug() is False, f"{v!r} should not enable debug"


# ---- invariant() ----

def test_invariant_passes_silently_on_true(monkeypatch, caplog):
    monkeypatch.setenv("SILICON_DEBUG", "1")
    logger = logging.getLogger("test.inv")
    with caplog.at_level(logging.ERROR, logger="test.inv"):
        assert invariant(True, "should not fire", logger=logger) is True
    # No ERROR line should have been emitted.
    assert not any(r.name == "test.inv" for r in caplog.records)


def test_invariant_raises_in_debug_mode(monkeypatch):
    monkeypatch.setenv("SILICON_DEBUG", "1")
    with pytest.raises(InvariantViolation, match="snarf"):
        invariant(False, "the snarf is missing")


def test_invariant_logs_in_production(monkeypatch, caplog):
    monkeypatch.delenv("SILICON_DEBUG", raising=False)
    logger = logging.getLogger("test.inv")
    with caplog.at_level(logging.ERROR, logger="test.inv"):
        result = invariant(False, "the snarf is missing", logger=logger)
    assert result is False  # caller learns the invariant failed
    # The log line was emitted.
    assert any("snarf" in r.message for r in caplog.records)
    # And is tagged with the right prefix.
    assert any("invariant_violation" in r.message for r in caplog.records)


def test_invariant_extra_dict_included_in_debug_message(monkeypatch):
    monkeypatch.setenv("SILICON_DEBUG", "1")
    with pytest.raises(InvariantViolation, match="viewer"):
        invariant(False, "bad", extra={"viewer": "red", "target": "u_b_1"})


# ---- reraise_in_debug() ----

def test_reraise_in_debug_rethrows_when_debug(monkeypatch):
    monkeypatch.setenv("SILICON_DEBUG", "1")
    logger = logging.getLogger("test.reraise")
    with pytest.raises(RuntimeError, match="boom"):
        try:
            raise RuntimeError("boom")
        except Exception:
            reraise_in_debug(logger, "caller message")


def test_reraise_in_debug_swallows_in_production(monkeypatch, caplog):
    monkeypatch.delenv("SILICON_DEBUG", raising=False)
    logger = logging.getLogger("test.reraise")
    with caplog.at_level(logging.ERROR, logger="test.reraise"):
        try:
            raise RuntimeError("boom")
        except Exception:
            reraise_in_debug(logger, "hook raised")
    # We fell through — the exception was swallowed.
    # A log record was produced.
    assert any("hook raised" in r.message for r in caplog.records)
    # The log level is exception (ERROR with traceback).
    msgs = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert msgs, "expected at least one ERROR record"


# ---- integration: fog attack in debug mode crashes ----

def test_fog_debug_mode_crashes_on_hidden_target_attack(monkeypatch):
    """End-to-end: set SILICON_DEBUG=1 and attack a fog-hidden
    target. The attack path must raise InvariantViolation rather
    than the friendlier ToolError."""
    from silicon_pantheon.server.engine.scenarios import load_scenario
    from silicon_pantheon.server.engine.state import Team, UnitStatus, Pos
    from silicon_pantheon.server.session import new_session
    from silicon_pantheon.server.tools.mutations import attack

    monkeypatch.setenv("SILICON_DEBUG", "1")

    state = load_scenario("01_tiny_skirmish")
    # Shove units apart so no red unit can see any blue unit.
    w, h = state.board.width, state.board.height
    blue_positions = [Pos(0, 0), Pos(0, 1), Pos(1, 0)]
    red_positions = [Pos(w - 1, h - 1), Pos(w - 1, h - 2), Pos(w - 2, h - 1)]
    bi, ri = iter(blue_positions), iter(red_positions)
    for u in list(state.units.values()):
        target = next(bi if u.owner is Team.BLUE else ri, None)
        if target is not None:
            u.pos = target
    state.active_player = Team.BLUE
    session = new_session(state, fog_of_war="classic")
    any_red = next(iter(state.units_of(Team.RED)))
    any_blue = next(iter(u for u in state.units_of(Team.BLUE) if u.alive))
    any_blue.status = UnitStatus.READY

    with pytest.raises(InvariantViolation, match="fog violation"):
        attack(session, Team.BLUE, any_blue.id, any_red.id)


def test_hook_exception_propagates_in_debug_mode(monkeypatch):
    """Session.notify_action swallows hook exceptions in production.
    In debug mode, the hook must re-raise so the bug surfaces."""
    from silicon_pantheon.server.engine.scenarios import load_scenario
    from silicon_pantheon.server.session import new_session

    monkeypatch.setenv("SILICON_DEBUG", "1")
    state = load_scenario("01_tiny_skirmish")
    session = new_session(state)

    def _bad_hook(session, result):
        raise RuntimeError("hook bug")

    session.action_hooks.append(_bad_hook)
    with pytest.raises(RuntimeError, match="hook bug"):
        session.notify_action({"type": "test"})


def test_hook_exception_swallowed_in_production(monkeypatch):
    """Production: hook exceptions are logged but don't break the
    game loop. Mirror of the test above."""
    from silicon_pantheon.server.engine.scenarios import load_scenario
    from silicon_pantheon.server.session import new_session

    monkeypatch.delenv("SILICON_DEBUG", raising=False)
    state = load_scenario("01_tiny_skirmish")
    session = new_session(state)

    def _bad_hook(session, result):
        raise RuntimeError("hook bug")

    session.action_hooks.append(_bad_hook)
    # Must not raise.
    session.notify_action({"type": "test"})
