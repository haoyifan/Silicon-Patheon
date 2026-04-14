"""Provider interface: drive one agent's turn against a Session."""

from __future__ import annotations

from abc import ABC, abstractmethod

from silicon_pantheon.lessons import Lesson
from silicon_pantheon.server.engine.state import Team
from silicon_pantheon.server.session import Session


class Provider(ABC):
    name: str = "base"

    @abstractmethod
    def decide_turn(self, session: Session, viewer: Team) -> None:
        """Play one full turn. Must call `end_turn` via the tool layer before
        returning (or the caller will force-end).
        """

    def on_match_start(self, session: Session, viewer: Team) -> None:
        """Optional hook: called once before the match begins."""

    def on_match_end(self, session: Session, viewer: Team) -> None:
        """Optional hook: called once after the match ends."""

    def summarize_match(
        self, session: Session, viewer: Team, scenario: str
    ) -> Lesson | None:
        """Optional hook: produce a post-match lesson from this team's view.

        Providers that can't reflect (random, stub) return None. The match
        orchestrator persists returned lessons via the LessonStore.
        """
        return None
