"""NetworkedAgent — provider-agnostic orchestrator for one player.

Composition: one `ProviderAdapter` (picked from the user's
credentials, defaulting to Anthropic) + the remote `ServerClient` +
the local scenario + strategy + lesson context. Every
per-turn interaction — building the turn prompt, dispatching tool
calls back through the server, surfacing reasoning — routes through
this class; the concrete LLM never leaks into the TUI.

Persistent-session default: the adapter opens its session on the
first `play_turn` and reuses it until `close()`, so the agent keeps
its chain-of-thought across turns within a single match.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from clash_of_odin.client.providers import (
    ProviderAdapter,
    ThoughtCallback,
    ToolSpec,
)
from clash_of_odin.client.transport import ServerClient
from clash_of_odin.harness.prompts import (
    build_system_prompt,
    build_turn_prompt_from_state_dict,
)
from clash_of_odin.lessons import Lesson, LessonStore
from clash_of_odin.server.engine.state import Team

# Canonical list of game-side tools exposed to the agent. Each entry:
# (name, description, JSON-schema input). connection_id is injected by
# ServerClient.call so it's not part of the schema the agent sees.
GAME_TOOLS: list[ToolSpec] = [
    ToolSpec(
        "get_state",
        "Get the current game state visible to you (fog-of-war filtered).",
        {"type": "object", "properties": {}, "required": []},
    ),
    ToolSpec(
        "get_unit",
        "Get a single unit's details by id.",
        {
            "type": "object",
            "properties": {"unit_id": {"type": "string"}},
            "required": ["unit_id"],
        },
    ),
    ToolSpec(
        "get_legal_actions",
        "Get the legal moves/attacks/heals/wait for one of your units.",
        {
            "type": "object",
            "properties": {"unit_id": {"type": "string"}},
            "required": ["unit_id"],
        },
    ),
    ToolSpec(
        "simulate_attack",
        "Predict attack outcome without mutating state.",
        {
            "type": "object",
            "properties": {
                "attacker_id": {"type": "string"},
                "target_id": {"type": "string"},
                "from_tile": {
                    "type": "object",
                    "properties": {"x": {"type": "integer"}, "y": {"type": "integer"}},
                    "required": ["x", "y"],
                },
            },
            "required": ["attacker_id", "target_id"],
        },
    ),
    ToolSpec(
        "get_threat_map",
        "For each tile, which visible enemy units can attack you there.",
        {"type": "object", "properties": {}, "required": []},
    ),
    ToolSpec(
        "get_history",
        "Recent action history.",
        {
            "type": "object",
            "properties": {"last_n": {"type": "integer", "default": 10}},
            "required": [],
        },
    ),
    ToolSpec(
        "get_coach_messages",
        "Drain unread coach messages for your team.",
        {
            "type": "object",
            "properties": {"since_turn": {"type": "integer", "default": 0}},
            "required": [],
        },
    ),
    ToolSpec(
        "move",
        "Move one of your ready units to a destination tile.",
        {
            "type": "object",
            "properties": {
                "unit_id": {"type": "string"},
                "dest": {
                    "type": "object",
                    "properties": {"x": {"type": "integer"}, "y": {"type": "integer"}},
                    "required": ["x", "y"],
                },
            },
            "required": ["unit_id", "dest"],
        },
    ),
    ToolSpec(
        "attack",
        "Attack an enemy unit from your current position.",
        {
            "type": "object",
            "properties": {
                "unit_id": {"type": "string"},
                "target_id": {"type": "string"},
            },
            "required": ["unit_id", "target_id"],
        },
    ),
    ToolSpec(
        "heal",
        "Heal an adjacent ally (Mage only).",
        {
            "type": "object",
            "properties": {
                "healer_id": {"type": "string"},
                "target_id": {"type": "string"},
            },
            "required": ["healer_id", "target_id"],
        },
    ),
    ToolSpec(
        "wait",
        "End this unit's turn without attacking or healing.",
        {
            "type": "object",
            "properties": {"unit_id": {"type": "string"}},
            "required": ["unit_id"],
        },
    ),
    ToolSpec(
        "end_turn",
        "Pass control to the opponent. Must be called to end your turn.",
        {"type": "object", "properties": {}, "required": []},
    ),
]


def _build_default_adapter(model: str) -> ProviderAdapter:
    """Factory for the provider adapter selected by the model id.

    Consults the credentials store + provider catalog to pick the
    right SDK. Fallbacks:
      - any claude-* model → Anthropic (subscription CLI)
      - any gpt-* / o*-* model → OpenAI (api key)
      - unknown → Anthropic (backward compatible default)
    API key resolution for OpenAI walks env var → keyring → inline
    key in the credentials file.
    """
    from clash_of_odin.client.credentials import (
        CredentialsError,
        ProviderCredential,
        load,
        resolve_key,
    )
    from clash_of_odin.shared.providers import get_provider

    # Pick provider by model-id prefix (or credentials default_provider
    # if the model itself doesn't disambiguate).
    model_lower = model.lower()
    provider_id: str
    if model_lower.startswith("claude") or model_lower.startswith("sonnet") or model_lower.startswith("opus"):
        provider_id = "anthropic"
    elif (
        model_lower.startswith("gpt")
        or model_lower.startswith("o1")
        or model_lower.startswith("o3")
        or model_lower.startswith("o4")
    ):
        provider_id = "openai"
    else:
        creds = load()
        provider_id = creds.default_provider or "anthropic"

    if provider_id == "anthropic":
        from clash_of_odin.client.providers.anthropic import AnthropicAdapter

        return AnthropicAdapter(model=model)

    if provider_id == "openai":
        from clash_of_odin.client.providers.openai import OpenAIAdapter

        # Resolve key: credentials file first, then raw env var.
        creds = load()
        cred = creds.providers.get("openai")
        api_key: str | None = None
        if cred is not None:
            try:
                api_key = resolve_key(cred)
            except CredentialsError:
                api_key = None
        if api_key is None:
            spec = get_provider("openai")
            if spec is not None and spec.env_var:
                import os

                api_key = os.environ.get(spec.env_var)
        if not api_key:
            raise RuntimeError(
                "OpenAI adapter selected but no API key could be resolved. "
                "Set OPENAI_API_KEY or configure credentials.json."
            )
        return OpenAIAdapter(model=model, api_key=api_key)

    # Unknown provider_id → fall back to Anthropic so existing
    # default-flow callers don't crash.
    from clash_of_odin.client.providers.anthropic import AnthropicAdapter

    return AnthropicAdapter(model=model)


class NetworkedAgent:
    """Drives one player's turns against a remote clash-serve."""

    def __init__(
        self,
        client: ServerClient,
        *,
        model: str,
        scenario: str,
        strategy: str | None = None,
        lessons_dir: Path | None = Path("lessons"),
        thoughts_callback: ThoughtCallback | None = None,
        time_budget_s: float = 90.0,
        adapter: ProviderAdapter | None = None,
    ):
        self.client = client
        self.model = model
        self.scenario = scenario
        self.strategy = strategy
        self.lessons_dir = lessons_dir
        self.thoughts_callback = thoughts_callback
        self.time_budget_s = time_budget_s
        self.adapter: ProviderAdapter = adapter or _build_default_adapter(model)

    async def close(self) -> None:
        try:
            await self.adapter.close()
        except Exception:
            pass

    # ---- tool dispatch ----

    async def _dispatch_tool(self, name: str, args: dict) -> dict:
        """Forward a tool call to the remote server.

        Unwraps the server's {ok, result | error} envelope so the agent
        sees raw game-tool payloads; {ok:false} surfaces as an error dict
        the SDK tool wrapper marks as isError.
        """
        result = await self.client.call(name, **args)
        if result.get("ok"):
            return result.get("result", result)
        return {"error": result.get("error", {})}

    # ---- state helpers ----

    async def _fetch_state(self) -> dict:
        r = await self.client.call("get_state")
        if not r.get("ok"):
            return {}
        return r.get("result", {})

    def _load_lessons(self) -> list:
        if self.lessons_dir is None:
            return []
        try:
            return LessonStore(self.lessons_dir).list_for_scenario(
                self.scenario, limit=5
            )
        except Exception:
            return []

    # ---- turn orchestration ----

    async def play_turn(self, viewer: Team, *, max_turns: int) -> dict:
        """Drive one half-turn: fetch state, build prompt, let the
        adapter run until the turn ends."""
        state = await self._fetch_state()
        base_prompt = build_turn_prompt_from_state_dict(state, viewer)
        # First turn vs subsequent: subsequent turns frame the state
        # as an update so the persistent transcript reads coherently.
        user_prompt = base_prompt
        system_prompt = build_system_prompt(
            team=viewer,
            max_turns=max_turns,
            strategy=self.strategy,
            lessons=self._load_lessons(),
        )

        await self.adapter.play_turn(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            tools=GAME_TOOLS,
            tool_dispatcher=self._dispatch_tool,
            on_thought=self.thoughts_callback,
            time_budget_s=self.time_budget_s,
        )

        return await self._fetch_state()

    async def summarize_match(self, viewer: Team) -> Lesson | None:
        """Post-match lesson writer. Saves to LessonStore if configured."""
        final_state = await self._fetch_state()
        history_r = await self.client.call("get_history", last_n=60)
        history = (history_r.get("result") or {}).get("history", [])

        lesson = await self.adapter.summarize_match(
            viewer=viewer,
            scenario=self.scenario,
            final_state=final_state,
            action_history=history,
        )
        if lesson is None:
            return None
        if self.lessons_dir is not None:
            try:
                LessonStore(self.lessons_dir).save(lesson)
            except Exception:
                pass
        return lesson
