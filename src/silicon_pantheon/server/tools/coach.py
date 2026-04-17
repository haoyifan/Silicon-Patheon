"""Coach communication tools."""

from __future__ import annotations

from ..engine.state import Team
from ..session import CoachMessage, Session


def send_to_agent(session: Session, viewer: Team, team: str, text: str) -> dict:
    target = Team(team)
    session.coach_queues[target].append(CoachMessage(turn=session.state.turn, text=text))
    session.log("coach_message", {"to": target.value, "text": text, "turn": session.state.turn})
    return {"ok": True, "queued_for": target.value, "turn": session.state.turn}
