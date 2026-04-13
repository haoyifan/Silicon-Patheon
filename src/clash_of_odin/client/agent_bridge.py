"""NetworkedAgent — drives a remote game via an LLM over ServerClient.

Architecture
------------
The agent sits on the client side and calls game tools via a local
SDK MCP server whose handlers forward to the remote clash-serve over
the existing ServerClient connection:

  LLM (Claude) <--MCP SDK--> local SDK MCP server
                               └─ tool handler per game tool
                                    └─ ServerClient.call()
                                        └─ MCP+SSE → clash-serve

Only one backend connection is used — the TUI's. Server-side auth,
state gating, and fog-of-war filtering apply to the agent exactly as
they do to a human pressing keys.

Memory model: **persistent session across the whole match**
-----------------------------------------------------------
A single `ClaudeSDKClient` is opened on the first `play_turn` and
reused for every subsequent turn until `close()`. Each turn sends one
new user message (the updated state snapshot) on top of the existing
transcript — the agent retains its plan, remembers what it already
tried, and can reflect on the opponent's last move without
re-deriving the position from scratch.

This is the opposite of the local `AnthropicProvider`'s fresh-per-turn
approach documented in DECISIONS.md. The escape hatch noted there —
"switch to ClaudeSDKClient if agents seem tactically incoherent across
turns" — is now the default for networked play.

Cost consequences: context grows monotonically across the match, so
very long matches (40+ turns with chatty agents) may run into the
model's context window. Mitigations (periodic summarization, tool-
result pruning) can be added as needed; the simple version is good
enough for standard scenarios.

Per-turn flow
-------------
`NetworkedAgent.play_turn(viewer)`:
  1. Open the persistent ClaudeSDKClient the first time, with the
     full system prompt (rules + strategy + lessons) baked in.
  2. Fetch filtered state via get_state for the turn-prompt snapshot.
  3. Send the turn prompt as a user message on the existing session.
  4. Iterate `receive_response()`; each tool call the agent makes
     forwards to the server. Stops when the turn ends (active_player
     flips away), the time budget trips, or the SDK returns a
     terminal ResultMessage.
  5. AssistantMessage text blocks are surfaced to an optional
     thoughts callback so the TUI's reasoning panel ticks live.
"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any, Awaitable, Callable

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    ResultMessage,
    TextBlock,
    create_sdk_mcp_server,
    query,
    tool,
)

from clash_of_odin.client.transport import ServerClient
from clash_of_odin.harness.prompts import (
    build_system_prompt,
    build_turn_prompt_from_state_dict,
    load_strategy,
)
from clash_of_odin.lessons import Lesson, LessonStore, slugify
from clash_of_odin.server.engine.state import Team

# The tools we expose to the agent. Each entry:
#   (name, description, {arg_name: jsonschema_fragment})
# `connection_id` is injected by ServerClient.call, not part of the
# schema the agent sees.
def _parse_lesson_json(text: str) -> dict | None:
    """Extract {title, slug, body} from model output; tolerant of
    code-fence wrappers and surrounding prose (mirrors the helper used
    by the local AnthropicProvider)."""
    if not text:
        return None
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.split("\n", 1)[1] if "\n" in stripped else ""
        if stripped.endswith("```"):
            stripped = stripped[: -len("```")]
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end == -1 or end < start:
        return None
    try:
        data = json.loads(stripped[start : end + 1])
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


GAME_TOOLS: list[tuple[str, str, dict[str, Any]]] = [
    (
        "get_state",
        "Get the current game state visible to you (fog-of-war filtered).",
        {"type": "object", "properties": {}, "required": []},
    ),
    (
        "get_unit",
        "Get a single unit's details by id.",
        {
            "type": "object",
            "properties": {"unit_id": {"type": "string"}},
            "required": ["unit_id"],
        },
    ),
    (
        "get_legal_actions",
        "Get the legal moves/attacks/heals/wait for one of your units.",
        {
            "type": "object",
            "properties": {"unit_id": {"type": "string"}},
            "required": ["unit_id"],
        },
    ),
    (
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
    (
        "get_threat_map",
        "For each tile, which visible enemy units can attack you there.",
        {"type": "object", "properties": {}, "required": []},
    ),
    (
        "get_history",
        "Recent action history.",
        {
            "type": "object",
            "properties": {"last_n": {"type": "integer", "default": 10}},
            "required": [],
        },
    ),
    (
        "get_coach_messages",
        "Drain unread coach messages for your team.",
        {
            "type": "object",
            "properties": {"since_turn": {"type": "integer", "default": 0}},
            "required": [],
        },
    ),
    (
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
    (
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
    (
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
    (
        "wait",
        "End this unit's turn without attacking or healing.",
        {
            "type": "object",
            "properties": {"unit_id": {"type": "string"}},
            "required": ["unit_id"],
        },
    ),
    (
        "end_turn",
        "Pass control to the opponent. Must be called to end your turn.",
        {"type": "object", "properties": {}, "required": []},
    ),
]


ThoughtCallback = Callable[[str], Awaitable[None]]


class NetworkedAgent:
    """Drives one client's turns against a remote clash-serve.

    Parameters
    ----------
    client : ServerClient
        Already-connected, already-authenticated client (IN_GAME state).
    model : str
        Claude model ID, e.g. 'claude-haiku-4-5'.
    strategy : str | None
        Optional strategy-playbook text to inject into the system prompt.
    lessons_dir : Path | None
        Where to look for prior lessons (matched by scenario name).
    thoughts_callback : async callable[(str), None] | None
        Called once per `AssistantMessage` text block with the plain
        reasoning text, so the TUI's reasoning panel can update live.
    time_budget_s : float
        Hard per-turn wall-clock cap.
    max_iterations : int
        Upper bound on tool-call rounds per turn.
    """

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
        max_iterations: int = 40,
    ):
        self.client = client
        self.model = model
        self.scenario = scenario
        self.strategy = strategy
        self.lessons_dir = lessons_dir
        self.thoughts_callback = thoughts_callback
        self.time_budget_s = time_budget_s
        self.max_iterations = max_iterations
        # Persistent-session state — opened on the first play_turn and
        # reused for every turn of the match.
        self._sdk_client: ClaudeSDKClient | None = None
        self._turn_count: int = 0

    async def close(self) -> None:
        """Tear down the persistent SDK session.

        Safe to call multiple times. GameScreen.on_exit hooks this up
        so leaving the screen (game over, concede, quit) cleans up the
        subprocess the SDK spawned."""
        if self._sdk_client is not None:
            try:
                await self._sdk_client.__aexit__(None, None, None)
            except Exception:
                pass
            self._sdk_client = None
            self._turn_count = 0

    async def summarize_match(self, viewer: Team) -> Lesson | None:
        """Ask the model for one lesson reflecting on the finished match.

        Mirrors the local AnthropicProvider.summarize_match but sources
        the final state + action history from the server via
        get_state / get_history instead of a local Session.
        """
        state = await self._fetch_state()
        history_r = await self.client.call("get_history", last_n=60)
        history = (history_r.get("result") or {}).get("history", [])
        winner = state.get("winner")
        if winner is None:
            outcome = "draw"
        else:
            outcome = "win" if winner == viewer.value else "loss"
        last = state.get("last_action") or {}
        reason = str(last.get("reason", "")) if isinstance(last, dict) else ""

        context = {
            "scenario": self.scenario,
            "you": viewer.value,
            "outcome": outcome,
            "reason": reason,
            "turns_played": state.get("turn"),
            "max_turns": state.get("max_turns"),
            "action_history": history[-60:],
            "final_units": state.get("units", []),
        }
        prompt = (
            f"You just finished a Clash of Odin match as {viewer.value} on scenario "
            f"'{self.scenario}'. Outcome: {outcome}"
            + (f" by {reason}" if reason else "")
            + ".\n\nReflect on ONE key decision or pattern that drove the outcome. "
            "Focus on generalizable tactical principle, not play-by-play.\n\n"
            "Respond with ONLY a JSON object (no prose, no code fences) with fields:\n"
            '  "title": short human title (<=80 chars)\n'
            '  "slug":  kebab-case phrase (<=60 chars)\n'
            '  "body":  markdown, <=400 words, with Situation and Lesson sections\n\n'
            f"Match context (JSON):\n```json\n{json.dumps(context, indent=2, default=str)}\n```\n"
        )
        opts = ClaudeAgentOptions(
            model=self.model,
            system_prompt="You are a tactical post-mortem writer. Return JSON only.",
            max_turns=1,
        )
        text = ""
        try:
            async for msg in query(prompt=prompt, options=opts):
                if isinstance(msg, AssistantMessage):
                    for block in msg.content:
                        if isinstance(block, TextBlock):
                            text += block.text
                if isinstance(msg, ResultMessage):
                    break
        except Exception:
            return None
        parsed = _parse_lesson_json(text)
        if parsed is None:
            return None
        title = parsed.get("title", "Untitled").strip() or "Untitled lesson"
        slug = slugify(parsed.get("slug", "").strip() or title)
        body = parsed.get("body", "").strip()
        if not body:
            return None
        lesson = Lesson(
            slug=slug,
            title=title,
            scenario=self.scenario,
            team=viewer.value,
            model=self.model,
            outcome=outcome,
            reason=reason,
            created_at=Lesson.now_iso(),
            body=body,
        )
        # Persist locally so priors accumulate across matches.
        if self.lessons_dir is not None:
            try:
                LessonStore(self.lessons_dir).save(lesson)
            except Exception:
                pass
        return lesson

    async def _ensure_session_started(
        self, viewer: Team, max_turns: int
    ) -> None:
        """Open the persistent ClaudeSDKClient on the first turn.

        System prompt (rules + strategy + lessons) is baked in at
        open-time so the SDK bundles it once and subsequent turns only
        send the new state delta as a user message.
        """
        if self._sdk_client is not None:
            return

        sdk_tools = self._make_sdk_tools()
        mcp_server = create_sdk_mcp_server(
            name="clash", version="1.0", tools=sdk_tools
        )
        allowed = [f"mcp__clash__{name}" for (name, _, _) in GAME_TOOLS]
        lessons = self._load_lessons()
        system_prompt = build_system_prompt(
            team=viewer,
            max_turns=max_turns,
            strategy=self.strategy,
            lessons=lessons,
        )
        opts = ClaudeAgentOptions(
            model=self.model,
            system_prompt=system_prompt,
            mcp_servers={"clash": mcp_server},
            allowed_tools=allowed,
            permission_mode="bypassPermissions",
            max_turns=self.max_iterations,
        )
        self._sdk_client = ClaudeSDKClient(options=opts)
        await self._sdk_client.__aenter__()

    async def play_turn(self, viewer: Team, *, max_turns: int) -> dict:
        """Play one full turn against the persistent session.

        The agent may emit several AssistantMessage blocks and multiple
        tool calls per turn; this method returns after end_turn has
        fired (server flips active_player away from `viewer`), the
        SDK returns a terminal ResultMessage, or the time budget
        trips.
        """
        await self._ensure_session_started(viewer, max_turns)
        assert self._sdk_client is not None  # for the type checker
        self._turn_count += 1

        state = await self._fetch_state()
        base_prompt = build_turn_prompt_from_state_dict(state, viewer)
        if self._turn_count == 1:
            prompt = base_prompt
        else:
            prompt = (
                "The opponent has taken their turn. Here's the updated "
                "state for your next half-turn. Your prior plan + what "
                "you already observed should still be in context — "
                "decide what to adjust based on what actually happened.\n\n"
                + base_prompt
            )

        start = time.time()
        try:
            await self._sdk_client.query(prompt)
            async for msg in self._sdk_client.receive_response():
                # Time budget + turn-ended guards FIRST so post-turn
                # chatter doesn't bleed into the next half.
                if time.time() - start > self.time_budget_s:
                    break
                if await self._is_turn_over(viewer):
                    break
                if isinstance(msg, AssistantMessage):
                    if self.thoughts_callback is not None:
                        for block in msg.content:
                            if isinstance(block, TextBlock) and block.text.strip():
                                try:
                                    await self.thoughts_callback(block.text)
                                except Exception:
                                    pass
                if isinstance(msg, ResultMessage):
                    break
        except Exception:
            # Any transport / SDK failure during the turn — bail out;
            # the server's turn-timer (when added) will eventually
            # force a turn end. We keep the session alive so the next
            # turn can still use it.
            pass

        return await self._fetch_state()

    # ---- helpers ----

    def _load_lessons(self) -> list:
        if self.lessons_dir is None:
            return []
        try:
            store = LessonStore(self.lessons_dir)
            return store.list_for_scenario(self.scenario, limit=5)
        except Exception:
            return []

    async def _fetch_state(self) -> dict:
        r = await self.client.call("get_state")
        if not r.get("ok"):
            return {}
        return r.get("result", {})

    async def _is_turn_over(self, viewer: Team) -> bool:
        r = await self.client.call("get_state")
        if not r.get("ok"):
            return True  # treat any error as done
        gs = r.get("result", {})
        if gs.get("status") == "game_over":
            return True
        return gs.get("active_player") != viewer.value

    def _make_sdk_tools(self) -> list:
        sdk_tools = []
        for name, description, schema in GAME_TOOLS:
            sdk_tools.append(self._wrap_tool(name, description, schema))
        return sdk_tools

    def _wrap_tool(self, name: str, description: str, schema: dict):
        """Build one SDK MCP tool that forwards to ServerClient.call."""
        client = self.client

        @tool(name, description, schema)
        async def _handler(args: dict) -> dict:
            try:
                result = await client.call(name, **(args or {}))
            except Exception as e:
                return {
                    "content": [
                        {"type": "text", "text": json.dumps({"error": str(e)})}
                    ],
                    "isError": True,
                }
            # The server wraps responses as {ok, result|error}. Unwrap so
            # the agent sees the raw game-tool payload (or an explicit
            # error object).
            if result.get("ok"):
                payload = result.get("result", result)
                return {
                    "content": [
                        {"type": "text", "text": json.dumps(payload, default=str)}
                    ]
                }
            return {
                "content": [
                    {"type": "text", "text": json.dumps(result.get("error", {}))}
                ],
                "isError": True,
            }

        return _handler
