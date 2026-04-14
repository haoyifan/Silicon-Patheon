"""Claude Agent SDK-backed provider.

Wraps the in-process tool layer as SDK MCP tools and drives the match
via a **persistent `ClaudeSDKClient` session** that spans every turn
of the match.

Memory model: the system prompt (rules + strategy + lessons) is sent
once at `on_match_start`. Each `decide_turn` sends a new user message
(the turn-prompt snapshot) onto the existing conversation. The agent
retains its plan, remembers tool results, and can reflect on the
opponent's move without re-deriving the position from scratch.

See DECISIONS.md (2026-04-13 entry) for the full trade-off
discussion. Summary: context grows monotonically across the match —
fine on Sonnet / Opus 1M, may want pruning on Haiku for 30+ turn
matches. Revert path: remove `_open_sdk_client` / `_close_sdk_client`
and put `create_sdk_mcp_server` + `query()` back inside `_async_turn`.
"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

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

from clash_of_odin.harness.prompts import build_system_prompt, build_turn_prompt, load_strategy
from clash_of_odin.harness.providers.base import Provider
from clash_of_odin.lessons import Lesson, LessonStore, slugify
from clash_of_odin.server.engine.state import Team
from clash_of_odin.server.session import Session
from clash_of_odin.server.tools import TOOL_REGISTRY, ToolError, call_tool

MCP_SERVER_NAME = "clash"


def _parse_lesson_json(text: str) -> dict | None:
    """Extract a {title, slug, body} object from model output.

    Tolerates surrounding prose or markdown code fences by locating the
    outermost JSON object. Returns None if nothing parseable was found.
    """
    if not text:
        return None
    # Strip common code-fence wrappers.
    stripped = text.strip()
    if stripped.startswith("```"):
        # drop first fence line and a trailing fence
        stripped = stripped.split("\n", 1)[1] if "\n" in stripped else ""
        if stripped.endswith("```"):
            stripped = stripped[: -len("```")]
    # Find the first '{' and the matching last '}'.
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end == -1 or end < start:
        return None
    try:
        data = json.loads(stripped[start : end + 1])
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    return data


def _sdk_tools_for(session: Session, viewer: Team):
    """Wrap each TOOL_REGISTRY entry as an SDK MCP tool bound to this session/viewer."""
    sdk_tools = []
    for name, spec in TOOL_REGISTRY.items():
        sdk_tools.append(_make_one(name, spec, session, viewer))
    return sdk_tools


def _make_one(name: str, spec: dict, session: Session, viewer: Team):
    description = spec["description"]
    schema = spec["input_schema"]

    @tool(name, description, schema)
    async def _handler(args):
        try:
            result = call_tool(session, viewer, name, args or {})
            return {"content": [{"type": "text", "text": json.dumps(result)}]}
        except ToolError as e:
            return {
                "content": [{"type": "text", "text": json.dumps({"error": str(e)})}],
                "isError": True,
            }

    return _handler


class AnthropicProvider(Provider):
    name = "anthropic"

    def __init__(
        self,
        model: str,
        strategy_path: str | Path | None = None,
        time_budget_s: float = 90.0,
        max_agent_iterations: int = 40,
        lessons_dir: str | Path | None = "lessons",
        max_injected_lessons: int = 5,
    ):
        self.model = model
        self.strategy = load_strategy(strategy_path)
        self.time_budget_s = time_budget_s
        self.max_agent_iterations = max_agent_iterations
        self.lessons_dir = Path(lessons_dir) if lessons_dir is not None else None
        self.max_injected_lessons = max_injected_lessons
        # Persistent-session state: one asyncio loop + one ClaudeSDKClient
        # per provider instance (i.e. per team), opened in on_match_start
        # and reused by every decide_turn call until on_match_end.
        self._loop: asyncio.AbstractEventLoop | None = None
        self._sdk_client: ClaudeSDKClient | None = None
        self._turn_count: int = 0

    # ---- match lifecycle ----

    def on_match_start(self, session: Session, viewer: Team) -> None:
        """Open the persistent SDK session.

        Using a dedicated event loop (rather than asyncio.run per turn)
        is required because the ClaudeSDKClient's stdio subprocess is
        tied to whichever loop created it; a fresh asyncio.run each
        turn would invalidate the client.
        """
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._open_sdk_client(session, viewer))

    def on_match_end(self, session: Session, viewer: Team) -> None:
        """Close the persistent SDK session + its event loop."""
        if self._loop is None:
            return
        try:
            self._loop.run_until_complete(self._close_sdk_client())
        except Exception as e:
            session.log("agent_error", {"team": viewer.value, "error": f"close: {e}"})
        finally:
            try:
                self._loop.close()
            except Exception:
                pass
            self._loop = None

    async def _open_sdk_client(self, session: Session, viewer: Team) -> None:
        sdk_tools = _sdk_tools_for(session, viewer)
        mcp_server = create_sdk_mcp_server(
            name=MCP_SERVER_NAME, version="0.1.0", tools=sdk_tools
        )
        lessons = self._load_lessons(session)
        system_prompt = build_system_prompt(
            team=viewer,
            max_turns=session.state.max_turns,
            strategy=self.strategy,
            lessons=lessons,
        )
        allowed = [f"mcp__{MCP_SERVER_NAME}__{n}" for n in TOOL_REGISTRY]
        opts = ClaudeAgentOptions(
            model=self.model,
            system_prompt=system_prompt,
            mcp_servers={MCP_SERVER_NAME: mcp_server},
            allowed_tools=allowed,
            permission_mode="bypassPermissions",
            max_turns=self.max_agent_iterations,
        )
        self._sdk_client = ClaudeSDKClient(options=opts)
        await self._sdk_client.__aenter__()

    async def _close_sdk_client(self) -> None:
        if self._sdk_client is not None:
            try:
                await self._sdk_client.__aexit__(None, None, None)
            except Exception:
                pass
            self._sdk_client = None

    # ---- per-turn ----

    def decide_turn(self, session: Session, viewer: Team) -> None:
        if self._loop is None or self._sdk_client is None:
            # on_match_start wasn't called (e.g. the test harness
            # instantiates the provider directly). Fall back to a
            # transient session for this one turn.
            asyncio.run(self._one_shot_turn(session, viewer))
            return
        self._loop.run_until_complete(self._async_turn(session, viewer))

    async def _async_turn(self, session: Session, viewer: Team) -> None:
        assert self._sdk_client is not None
        start = time.time()
        turn_at_start = session.state.turn
        self._turn_count += 1

        base_prompt = build_turn_prompt(session, viewer)
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

        try:
            await self._sdk_client.query(prompt)
            async for msg in self._sdk_client.receive_response():
                # Guard FIRST so post-end_turn chatter doesn't bleed
                # into the opponent's half.
                if session.state.active_player is not viewer:
                    break
                if time.time() - start > self.time_budget_s:
                    break
                if isinstance(msg, AssistantMessage):
                    for block in msg.content:
                        if isinstance(block, TextBlock) and block.text.strip():
                            session.add_thought(
                                viewer, block.text, turn=turn_at_start
                            )
                if isinstance(msg, ResultMessage):
                    break
        except Exception as e:
            session.log("agent_error", {"team": viewer.value, "error": str(e)})

        if session.state.active_player is viewer and session.state.turn == turn_at_start:
            self._force_end_turn(session, viewer)

    async def _one_shot_turn(self, session: Session, viewer: Team) -> None:
        """Fallback for callers that skip the on_match_start/_end hooks.

        Behaves like the pre-persistent implementation: one query() per
        turn, no cross-turn memory. Keeps tests that instantiate
        AnthropicProvider directly (without going through run_match)
        working without rearranging their lifecycle.
        """
        start = time.time()
        turn_at_start = session.state.turn
        sdk_tools = _sdk_tools_for(session, viewer)
        mcp_server = create_sdk_mcp_server(
            name=MCP_SERVER_NAME, version="0.1.0", tools=sdk_tools
        )
        lessons = self._load_lessons(session)
        system_prompt = build_system_prompt(
            team=viewer,
            max_turns=session.state.max_turns,
            strategy=self.strategy,
            lessons=lessons,
        )
        turn_prompt = build_turn_prompt(session, viewer)
        allowed = [f"mcp__{MCP_SERVER_NAME}__{n}" for n in TOOL_REGISTRY]
        opts = ClaudeAgentOptions(
            model=self.model,
            system_prompt=system_prompt,
            mcp_servers={MCP_SERVER_NAME: mcp_server},
            allowed_tools=allowed,
            permission_mode="bypassPermissions",
            max_turns=self.max_agent_iterations,
        )
        try:
            async for msg in query(prompt=turn_prompt, options=opts):
                if session.state.active_player is not viewer:
                    break
                if time.time() - start > self.time_budget_s:
                    break
                if isinstance(msg, AssistantMessage):
                    for block in msg.content:
                        if isinstance(block, TextBlock) and block.text.strip():
                            session.add_thought(
                                viewer, block.text, turn=turn_at_start
                            )
                if isinstance(msg, ResultMessage):
                    break
        except Exception as e:
            session.log("agent_error", {"team": viewer.value, "error": str(e)})
        if session.state.active_player is viewer and session.state.turn == turn_at_start:
            self._force_end_turn(session, viewer)

    def _load_lessons(self, session: Session) -> list[Lesson]:
        """Load the most recent lessons for this session's scenario."""
        if self.lessons_dir is None or session.scenario is None:
            return []
        try:
            store = LessonStore(self.lessons_dir)
            return store.list_for_scenario(
                session.scenario, limit=self.max_injected_lessons
            )
        except Exception as e:
            session.log("lessons_load_error", {"error": str(e)})
            return []

    # ---- post-match reflection ----

    def summarize_match(
        self, session: Session, viewer: Team, scenario: str
    ) -> Lesson | None:
        """Ask the model for one lesson learned from this team's perspective.

        Uses a tool-less `query()` call so the model only produces text. We
        request a JSON object {title, slug, body} and parse it; on any
        parse failure we fall back to a best-effort slug.
        """
        try:
            return asyncio.run(self._async_summarize(session, viewer, scenario))
        except Exception as e:
            session.log("summarize_error", {"team": viewer.value, "error": str(e)})
            return None

    async def _async_summarize(
        self, session: Session, viewer: Team, scenario: str
    ) -> Lesson | None:
        winner = session.state.winner
        if winner is None:
            outcome = "draw"
        else:
            outcome = "win" if winner is viewer else "loss"

        last = session.state.last_action or {}
        reason = str(last.get("reason", "")) if isinstance(last, dict) else ""

        own_thoughts = [
            {"turn": t.turn, "text": t.text}
            for t in session.thoughts
            if t.team is viewer
        ]
        history = session.state.history  # full action log (both teams)

        context = {
            "scenario": scenario,
            "you": viewer.value,
            "outcome": outcome,
            "reason": reason,
            "turns_played": session.state.turn,
            "max_turns": session.state.max_turns,
            "final_units": {
                "blue": [
                    {"id": u.id, "class": u.class_, "hp": u.hp}
                    for u in session.state.units_of(Team.BLUE)
                ],
                "red": [
                    {"id": u.id, "class": u.class_, "hp": u.hp}
                    for u in session.state.units_of(Team.RED)
                ],
            },
            "your_reasoning": own_thoughts[-40:],  # cap for prompt size
            "action_history": history[-60:],
        }

        prompt = (
            f"You just finished a Clash of Odin match as {viewer.value} on scenario "
            f"'{scenario}'. Outcome: {outcome}"
            + (f" by {reason}" if reason else "")
            + ".\n\n"
            "Reflect on ONE key decision or pattern that drove the outcome — "
            "something a future player of this scenario should internalize. "
            "Focus on generalizable tactical principle, not play-by-play narration.\n\n"
            "Respond with ONLY a JSON object (no prose, no code fences) with fields:\n"
            '  "title": short human title (<= 80 chars)\n'
            '  "slug":  filesystem-safe kebab-case phrase (<= 60 chars) that names the lesson\n'
            '  "body":  markdown, <= 400 words, with a "Situation" and "Lesson" section\n\n'
            "Match context (JSON):\n"
            f"```json\n{json.dumps(context, indent=2, default=str)}\n```\n"
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
        except Exception as e:
            session.log("summarize_error", {"team": viewer.value, "error": str(e)})
            return None

        parsed = _parse_lesson_json(text)
        if parsed is None:
            return None

        title = parsed.get("title", "Untitled lesson").strip() or "Untitled lesson"
        slug_raw = parsed.get("slug", "").strip()
        slug = slugify(slug_raw or title)
        body = parsed.get("body", "").strip()
        if not body:
            return None

        return Lesson(
            slug=slug,
            title=title,
            scenario=scenario,
            team=viewer.value,
            model=self.model,
            outcome=outcome,
            reason=reason,
            created_at=Lesson.now_iso(),
            body=body,
        )

    def _force_end_turn(self, session: Session, viewer: Team) -> None:
        # Wait any mid-action units, then end turn.
        for u in list(session.state.units_of(viewer)):
            if u.status.value == "moved":
                try:
                    call_tool(session, viewer, "wait", {"unit_id": u.id})
                except ToolError:
                    pass
        try:
            call_tool(session, viewer, "end_turn", {})
        except ToolError:
            pass
        session.log("forced_end_turn", {"team": viewer.value})
