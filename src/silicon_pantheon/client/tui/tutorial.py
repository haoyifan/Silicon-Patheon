"""Tutorial overlay system.

Three-stage progressive tutorial (lobby → room → game) shown to
first-time players. Each stage is a sequence of modal steps that
explain the relevant UI. The overlay blocks all input except:

    →/l/Enter   next step
    ←/h         previous step
    s/Esc       skip (close tutorial, mark stage as done)

Completion state is persisted to ~/.silicon-pantheon/tutorial_state.json
so tutorials don't replay across sessions. The lobby screen offers
a "replay tutorial" key that resets all stages.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from rich.align import Align
from rich.console import Group, RenderableType
from rich.panel import Panel as RichPanel
from rich.text import Text

from silicon_pantheon.client.locale import t

log = logging.getLogger("silicon.tui.tutorial")

_STATE_PATH = Path.home() / ".silicon-pantheon" / "tutorial_state.json"


# ---- persistence --------------------------------------------------------


@dataclass
class TutorialState:
    lobby_done: bool = False
    room_done: bool = False
    game_done: bool = False

    def is_stage_done(self, stage: str) -> bool:
        return getattr(self, f"{stage}_done", False)

    def mark_done(self, stage: str) -> None:
        setattr(self, f"{stage}_done", True)
        save_tutorial_state(self)

    def reset_all(self) -> None:
        self.lobby_done = False
        self.room_done = False
        self.game_done = False
        save_tutorial_state(self)


def load_tutorial_state() -> TutorialState:
    try:
        if _STATE_PATH.is_file():
            data = json.loads(_STATE_PATH.read_text(encoding="utf-8"))
            return TutorialState(
                lobby_done=bool(data.get("lobby_done", False)),
                room_done=bool(data.get("room_done", False)),
                game_done=bool(data.get("game_done", False)),
            )
    except Exception:
        pass
    return TutorialState()


def save_tutorial_state(state: TutorialState) -> None:
    try:
        _STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        _STATE_PATH.write_text(
            json.dumps({
                "lobby_done": state.lobby_done,
                "room_done": state.room_done,
                "game_done": state.game_done,
            }),
            encoding="utf-8",
        )
    except Exception:
        log.debug("Failed to save tutorial state", exc_info=True)


# ---- tutorial step definition -------------------------------------------


@dataclass(frozen=True)
class TutorialStep:
    """One step in a tutorial sequence."""
    # Locale key for the title (e.g., "tutorial.lobby.step1_title").
    title_key: str
    # Locale key for the body text.
    body_key: str
    # Optional: name of the panel to highlight (border turns yellow).
    # Values: "map", "player", "reasoning", "coach", "actions", etc.
    # The screen checks this and changes the highlighted panel's border.
    highlight_panel: str | None = None


# ---- tutorial content per stage -----------------------------------------


LOBBY_STEPS: list[TutorialStep] = [
    TutorialStep(
        "tutorial.lobby.welcome_title",
        "tutorial.lobby.welcome_body",
    ),
    TutorialStep(
        "tutorial.lobby.rooms_title",
        "tutorial.lobby.rooms_body",
    ),
    TutorialStep(
        "tutorial.lobby.actions_title",
        "tutorial.lobby.actions_body",
    ),
    TutorialStep(
        "tutorial.lobby.replay_title",
        "tutorial.lobby.replay_body",
    ),
]

ROOM_STEPS: list[TutorialStep] = [
    TutorialStep(
        "tutorial.room.map_title",
        "tutorial.room.map_body",
        highlight_panel="map",
    ),
    TutorialStep(
        "tutorial.room.player_title",
        "tutorial.room.player_body",
        highlight_panel="player",
    ),
    TutorialStep(
        "tutorial.room.description_title",
        "tutorial.room.description_body",
        highlight_panel="description",
    ),
    TutorialStep(
        "tutorial.room.welcome_title",
        "tutorial.room.welcome_body",
        highlight_panel="actions",
    ),
    TutorialStep(
        "tutorial.room.scenario_title",
        "tutorial.room.scenario_body",
        highlight_panel="actions",
    ),
    TutorialStep(
        "tutorial.room.config_title",
        "tutorial.room.config_body",
        highlight_panel="actions",
    ),
    TutorialStep(
        "tutorial.room.strategy_title",
        "tutorial.room.strategy_body",
        highlight_panel="actions",
    ),
    TutorialStep(
        "tutorial.room.lessons_title",
        "tutorial.room.lessons_body",
        highlight_panel="actions",
    ),
    TutorialStep(
        "tutorial.room.ready_title",
        "tutorial.room.ready_body",
        highlight_panel="actions",
    ),
]

GAME_STEPS: list[TutorialStep] = [
    TutorialStep(
        "tutorial.game.welcome_title",
        "tutorial.game.welcome_body",
    ),
    TutorialStep(
        "tutorial.game.map_title",
        "tutorial.game.map_body",
        highlight_panel="map",
    ),
    TutorialStep(
        "tutorial.game.units_title",
        "tutorial.game.units_body",
        highlight_panel="player",
    ),
    TutorialStep(
        "tutorial.game.reasoning_title",
        "tutorial.game.reasoning_body",
        highlight_panel="reasoning",
    ),
    TutorialStep(
        "tutorial.game.coach_title",
        "tutorial.game.coach_body",
        highlight_panel="coach",
    ),
    TutorialStep(
        "tutorial.game.flow_title",
        "tutorial.game.flow_body",
    ),
]


# ---- overlay widget -----------------------------------------------------


class TutorialOverlay:
    """Modal overlay that walks through tutorial steps.

    While active, the hosting screen should:
    1. Call overlay.render() to get the modal renderable
    2. Route all keys through overlay.handle_key()
    3. Check overlay.is_done to know when to remove it
    4. Read overlay.highlight_panel to know which panel to highlight
    """

    def __init__(
        self,
        steps: list[TutorialStep],
        stage: str,
        locale: str = "en",
        on_complete: Any = None,
    ):
        self.steps = steps
        self.stage = stage
        self.locale = locale
        self._step_idx = 0
        self.is_done = False
        self._on_complete = on_complete

    @property
    def highlight_panel(self) -> str | None:
        if self._step_idx < len(self.steps):
            return self.steps[self._step_idx].highlight_panel
        return None

    def _build_content(self) -> tuple[Text, Text]:
        """Build the body text and footer for the current step."""
        lc = self.locale
        step = self.steps[self._step_idx]
        total = len(self.steps)
        idx = self._step_idx + 1

        title_text = t(step.title_key, lc)
        body_text = t(step.body_key, lc)

        body = Text(no_wrap=False, overflow="fold")
        body.append(f"{title_text}\n", style="bold yellow")
        body.append(body_text.strip(), style="white")
        body.append("\n")

        # Progress indicator
        dots = ""
        for i in range(total):
            dots += "●" if i == self._step_idx else "○"
        body.append(f"{dots} ({idx}/{total})  ", style="dim")
        body.append(t("tutorial.nav", lc), style="dim")

        return body, Text("")

    def render(self) -> RenderableType:
        """Full-screen centered modal (used by lobby tutorial)."""
        body, _ = self._build_content()
        return Align.center(
            RichPanel(
                body,
                title=f"📖 {t('tutorial.title', self.locale)}",
                border_style="bright_yellow",
                padding=(1, 2),
                width=56,
            ),
            vertical="middle",
        )

    def render_inline(self) -> RenderableType:
        """Compact inline box for embedding inside a panel.

        Used by room and game panels — the tutorial renders inside
        the panel it's explaining, not as a separate overlay."""
        body, _ = self._build_content()
        return RichPanel(
            body,
            title=f"📖 {t('tutorial.title', self.locale)}",
            border_style="bright_yellow",
            padding=(0, 1),
        )

    def handle_key(self, key: str) -> None:
        """Process a keypress. Updates internal state.
        Check self.is_done after calling."""
        if key in ("right", "l", "enter"):
            if self._step_idx < len(self.steps) - 1:
                self._step_idx += 1
            else:
                # Last step → done
                self._finish()
        elif key in ("left", "h"):
            if self._step_idx > 0:
                self._step_idx -= 1
        elif key in ("s", "esc"):
            self._finish()

    def _finish(self) -> None:
        self.is_done = True
        if self._on_complete:
            self._on_complete()

    def targets_panel(self, panel_name: str) -> bool:
        """Check if the current step targets a specific panel."""
        return (
            not self.is_done
            and self.highlight_panel == panel_name
        )
