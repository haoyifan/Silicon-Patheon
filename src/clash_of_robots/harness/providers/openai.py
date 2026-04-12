"""OpenAI provider — stub for Phase 7 cross-model matches.

Not implemented in MVP; left as a scaffold. To fill in:

1. `pip install openai` (already in pyproject if you add it).
2. Read `OPENAI_API_KEY` from env.
3. Use the Responses API or Chat Completions with tool-calling; convert each
   entry in `clash_of_robots.server.tools.TOOL_REGISTRY` to OpenAI's tool schema.
4. Follow the same loop shape as `AnthropicProvider._async_turn`:
    - build system + per-turn prompt
    - iterate LLM responses, dispatch tool calls via `server.tools.call_tool`,
      feed results back, break when `end_turn` tool flips `session.state.active_player`.

Keeping this separate (rather than one big file) keeps provider code isolated so
cross-model matches become a localized change.
"""

from __future__ import annotations

from clash_of_robots.harness.providers.base import Provider
from clash_of_robots.server.engine.state import Team
from clash_of_robots.server.session import Session


class OpenAIProvider(Provider):
    name = "openai"

    def __init__(self, model: str, **_kwargs):
        self.model = model

    def decide_turn(self, session: Session, viewer: Team) -> None:  # pragma: no cover
        raise NotImplementedError(
            "OpenAIProvider is a Phase 7 stub. Set OPENAI_API_KEY and implement "
            "the OpenAI tool-calling loop. See this module's docstring for the recipe."
        )
