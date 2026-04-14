# Decisions Log

Running log of design and implementation calls made by Claude during build-out
of SiliconPantheon. Each entry: what was decided, why, and any reversal cost if
we later disagree.

Format:
```
## YYYY-MM-DD — Short title
**Decision:** ...
**Why:** ...
**Reversal cost:** low / medium / high — what would change if we undo this.
```

---

## 2026-04-12 — Project & tooling baseline
**Decision:** Project named "SiliconPantheon", Python package `silicon_pantheon`,
Python 3.12, `uv` for env management, `ruff` for lint+format, `pyright` (basic
mode) for type checking enforced from Phase 1, `pytest` for tests, src layout
(`src/silicon_pantheon/...`).
**Why:** User explicitly chose name, Python 3.12, ruff, and asked for early type
checking. src layout is the modern Python default and prevents the common
"importing from project root" foot-gun.
**Reversal cost:** Low for tooling swaps; medium for package name (touches
imports everywhere).

## 2026-04-12 — Game scenarios as YAML in `games/<name>/config.yaml`
**Decision:** Scenarios live under `games/<scenario_name>/config.yaml`, each
folder self-contained with terrain + armies + starting positions + win rules +
optional README. Replaces the earlier `maps/*.json` plan.
**Why:** User asked for flexibility to iterate from simple to complex scenarios
for backtesting. YAML is more hand-editable than JSON. Folder per scenario lets
each ship with its own README explaining what it tests.
**Reversal cost:** Low — scenario loader is a single module.

## 2026-04-12 — Orchestrator-driven turn handoff (Option C) for MVP
**Decision:** Phase 3-7 use the orchestrator to invoke each harness's
`play_turn()` synchronously. MCP server-initiated notifications (Option B) are
deferred to Phase 8 when remote/server play matters.
**Why:** Same process tree, simplest mental model, ~10 lines of code. User
confirmed "local first, but eventually a server."
**Reversal cost:** Medium — Phase 8 will need to add an MCP notification
listener to the harness loop.

## 2026-04-12 — Claude Agent SDK as primary harness (Phases 5-6)
**Decision:** Use Claude Agent SDK with the user's existing Claude Max
subscription auth. No `ANTHROPIC_API_KEY` required. Add provider-specific
clients (OpenAI, etc.) only in Phase 7 for cross-model matches.
**Why:** User has Max subscription; SDK reuses Claude Code auth; bonus that the
SDK provides agent loop / tool calling / compaction primitives for free.
**Reversal cost:** Low — provider abstraction (`harness/providers/base.py`)
isolates the choice. Can swap to direct Anthropic SDK or roll-your-own later.

## 2026-04-12 — Default game rules (gaps the user accepted with "sounds good")
**Decision:** Recorded in `GAME_DESIGN.md`:
- Counter range = defender's `RNG`; doubling applies on counters.
- Mage cannot self-heal; heals adjacent (Manhattan 1) ally only; counts as action.
- No stacking; one unit per tile.
- Action order within a turn: any unit order, but each unit's move-then-act is
  contiguous; once `done`, locked for the turn.
- Blue goes first; tournament code swaps colors across rounds.
- Home forts owned at start; mid-map forts neutral.
**Why:** User confirmed all defaults. Captured here so Phase 1 implementation
has a single source of truth and any future disagreement is easy to spot.
**Reversal cost:** Low for any individual rule (engine code is small); medium
if multiple change at once (test suite needs updates).

## 2026-04-12 — Tool layer is callable directly; MCP stdio is a thin wrapper
**Decision:** The game tools (`get_state`, `move`, `attack`, ...) are plain
Python functions living in `server/tools/` with a shared tool registry. They
operate on a `Session` object that bundles `GameState` + coach message queues +
replay writer. The MCP stdio server (`server/main.py`) is a thin wrapper that
exposes these same tools over the MCP protocol for remote/future use. For
phases 3-7 the orchestrator calls the tool registry **directly in-process** —
no subprocess, no stdio round-trip. This avoids the fundamental stdio-is-1:1
constraint (two agents cannot share one stdio MCP server) while keeping a real
MCP server available for Phase 8 remote play.
**Why:** Stdio MCP only supports one client per server process. Two agents
playing the same match would require either HTTP/SSE transport (Phase 8 work)
or running two server instances with synced state (complex, fragile). The
orchestrator-driven turn model (decision above) already serializes actions, so
in-process tool calls are sufficient for MVP; the protocol layer becomes
valuable only when agents are remote.
**Reversal cost:** Low — because tools live on a registry with a uniform
interface, swapping "direct call" for "call via MCP client" is localized.

## 2026-04-12 — Tools live together in `server/tools/__init__.py`
**Decision:** All tool functions in one module file rather than one file per
tool (as originally sketched in PLAN.md).
**Why:** Each tool is ~10-30 lines; splitting into 8+ files adds import noise
and makes cross-tool coordination harder for no real benefit. The registry
pattern already provides discoverability.
**Reversal cost:** Trivial — move functions into per-tool files if one ever
grows large.

## 2026-04-12 — Agents are fresh-per-turn, not persistent sessions
**Decision:** `AnthropicProvider.decide_turn` calls the SDK's one-shot `query()`
each turn. No conversation history carries between turns — the agent is
re-spawned fresh every turn with the same system prompt (rules + strategy) and
a new per-turn prompt containing a current state snapshot.

Cross-turn continuity is provided by the **server-side state**, not the
agent's context: the `GameState`, coach message queue, and action history
(retrievable via `get_history`) persist across turns. What does *not* persist
is the agent's chain-of-thought, multi-turn plans, or internal reasoning.

**Why:**
- No context bloat — a 30-turn match stays ~20-30k tokens per turn instead of
  ballooning to ~450k by turn 30.
- No compaction required — summarizing tactical reasoning is hard and easy to
  get wrong.
- Failure isolation — a bad turn (e.g., tool-call loop) doesn't poison
  subsequent turns.
- Board state often *is* the plan's memory: a cavalry 2 tiles from the enemy
  fort telegraphs its own intent.

**Reversal cost:** Low-medium. Swap `query()` → `ClaudeSDKClient` (persistent),
instantiate once per match in `__init__`, send a "your turn" message per
`decide_turn`. Add compaction when context nears 80% full. ~50 lines in
`anthropic.py`.

**TODO for future evaluation:** Once real agent matches have been played,
decide whether tactical incoherence across turns justifies the switch. If
agents seem to "forget what they were doing," flip to persistent sessions. If
they play coherently, stay fresh-per-turn.

## 2026-04-13 — Networked agent uses a persistent session (reversal)

**Decision:** The networked `NetworkedAgent` in `client/agent_bridge.py`
opens one `ClaudeSDKClient` on the first `play_turn` and reuses it for
every subsequent turn until `close()`. Each turn sends a new user
message (updated state snapshot) onto the existing transcript; the
agent retains its prior plan, remembers tool results, and can reflect
on the opponent's move without re-deriving the position.

**Why the flip, specifically for networked play:**
- The local `AnthropicProvider` is still fresh-per-turn — it's fast,
  cheap, and ideal for running hundreds of development matches.
- The networked flow is meant for humans (or friends' agents) to watch
  a match unfold; tactical incoherence between turns reads as the
  agent "forgetting what it just did." Persistent session eliminates
  that class of bug.
- Context budget: matches on these scenarios top out around 20 turns,
  40 half-turns, so a persistent conversation stays well within Sonnet
  / Opus 1M context even with chatty reasoning.

**Trade-offs:**
- Token cost grows across a match (full history replayed each turn),
  so a 20-turn match with 10 tool calls per turn can climb to 100k+
  context tokens by the end.
- A bad turn can poison later turns; if that becomes an issue, add
  a "new subtree" escape hatch (start a fresh client mid-match).
- Post-match summarization still uses a one-shot `query()` — by the
  time we summarize, we want an unbiased post-mortem, not a
  continuation of the in-match thread.

**Reversal cost:** Low. Revert `play_turn` to re-open a fresh `query()`
per call and drop the `ClaudeSDKClient` lifecycle from `close()`.

## 2026-04-12 — Multi-provider agents + flexible scenarios

**Decision:** Added two major capability bundles in one push:

1. **Multi-provider agent support** via a `ProviderAdapter` protocol.
   Anthropic (Claude SDK) and OpenAI (Chat Completions + function
   calling) land initially; others plug in behind the same interface.
   Keys resolve through `~/.silicon-pantheon/credentials.json` using
   `env:` / `keyring:` refs — no inline secrets by default.

2. **Flexible scenarios.** A scenario's YAML can now declare custom
   unit classes, custom terrain types (with effects_plugin for
   arbitrary on-tile behavior), a declarative `win_conditions:` DSL
   (7 built-in rule types + `plugin` escape hatch), a `narrative:`
   block with `on_turn_start`/`on_unit_killed` events, and `rules.py`
   plugin callables (operator-trusted, no sandbox). `PROTOCOL_VERSION`
   and `SUPPORTED_SCHEMA_VERSION` gates refuse loads that the engine
   can't understand so future fields never get silently dropped.

Journey to the West ships as the flagship scenario exercising every
knob above (10 custom classes, 4 custom terrain types, 4 stacked
win conditions, 5 narrative events, a reinforcement-spawning plugin).

**Why:** the first-party Claude Sonnet agent loop is not the only
interesting client; and a single balanced map is too narrow a stage
for the agent coaching we care about. Both had been hardcoded in
Phase 1–5; separating them lets scenario authors and provider authors
move independently.

**Reversal cost:** Medium — provider code is behind the adapter
boundary and easy to remove; scenarios without new blocks keep
loading unchanged thanks to the schema gate and legacy fallbacks.
The big revert would be rolling `state._win_conditions`,
`state._plugin_namespace`, and `state._narrative` back to hardcoded
equivalents.

## 2026-04-12 — Python 3.13 in practice (pyproject requires ≥3.12)
**Decision:** uv selected Python 3.13.5 on this machine; pyproject pins ≥3.12.
No code changes needed; 3.12-only features (match, generic syntax) all work.
**Why:** ≥3.12 constraint is satisfied by 3.13; uv picks the best available.
**Reversal cost:** None.
