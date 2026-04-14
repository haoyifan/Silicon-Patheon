# Implementation Plan — SiliconPantheon

End-to-end plan for building the agent-vs-agent tactics game described in
`GAME_DESIGN.md`. Each phase ends with something runnable and demoable. Don't
move to the next phase until the current one demos cleanly.

**Project name:** SiliconPantheon
**Python package:** `silicon_pantheon`

## Repo structure

```
agent-game/
├── README.md
├── DESIGN.md                          # original brain dump
├── GAME_DESIGN.md                     # design spec
├── PLAN.md                            # this file
├── DECISIONS.md                       # log of design calls made during implementation
├── pyproject.toml                     # uv-managed; ruff + pyright configured
│
├── src/silicon_pantheon/
│   ├── __init__.py
│   ├── server/                        # MCP server — game engine + tool wrappers
│   │   ├── __init__.py
│   │   ├── main.py                    # stdio entrypoint
│   │   ├── schemas.py                 # JSON schemas for all tools
│   │   ├── engine/                    # pure Python game logic, no MCP
│   │   │   ├── __init__.py
│   │   │   ├── state.py               # GameState, Unit, Tile dataclasses
│   │   │   ├── units.py               # class definitions, stat tables
│   │   │   ├── board.py               # terrain, pathfinding
│   │   │   ├── combat.py              # damage, counter, doubling
│   │   │   ├── rules.py               # legal actions, apply, win check
│   │   │   ├── scenarios.py           # load games/<name>/config.yaml
│   │   │   └── replay.py              # match log writer
│   │   └── tools/                     # one file per MCP tool
│   │       ├── __init__.py
│   │       ├── get_state.py
│   │       ├── get_legal_actions.py
│   │       ├── simulate_attack.py
│   │       ├── move.py
│   │       ├── attack.py
│   │       ├── heal.py
│   │       ├── end_turn.py
│   │       └── coach.py
│   ├── harness/                       # agent runner
│   │   ├── __init__.py
│   │   ├── harness.py                 # AgentHarness loop
│   │   ├── prompts.py                 # system prompt + per-turn template
│   │   ├── compaction.py              # history summarization
│   │   ├── budgets.py                 # token/time enforcement
│   │   └── providers/
│   │       ├── __init__.py
│   │       ├── base.py                # provider interface
│   │       ├── random.py              # picks random legal action
│   │       ├── anthropic.py
│   │       └── openai.py
│   ├── renderer/                      # terminal UI
│   │   ├── __init__.py
│   │   ├── tui.py                     # main loop, rich.Live
│   │   ├── board_view.py              # ASCII grid
│   │   ├── sidebar.py                 # unit details, last action, log
│   │   └── coach_input.py             # human types advice
│   └── match/                         # orchestrator
│       ├── __init__.py
│       ├── run_match.py               # CLI entrypoint
│       └── config.py                  # budgets, fog, etc.
│
├── games/                             # game scenarios (terrain + armies + rules)
│   ├── README.md                      # how to define a scenario
│   ├── 01_tiny_skirmish/
│   │   ├── config.yaml
│   │   └── README.md
│   ├── 02_basic_mirror/
│   │   └── config.yaml
│   └── 03_full_armies/
│       └── config.yaml
│
├── strategies/                        # per-agent playbooks (markdown)
│   ├── README.md
│   ├── aggressive_rush.md
│   ├── defensive_chokepoint.md
│   └── balanced.md
│
├── agents/                            # optional YAML agent configs
│   └── README.md
│
├── replays/                           # gitignored
│
└── tests/
    ├── test_combat.py
    ├── test_legal_actions.py
    ├── test_rules.py
    ├── test_scenarios.py
    └── test_match_smoke.py
```

### Structural choices

- `src/silicon_pantheon/` is a single Python package using the **src layout**.
  Subpackages (`server/`, `harness/`, `renderer/`, `match/`) keep concerns
  separated but share types and utilities cleanly.
- `server/engine/` is **pure Python with no MCP knowledge**. Game engine is
  unit-testable without a server. `server/tools/` is the thin MCP wrapper.
- `harness/providers/` with a `base.py` interface keeps provider-specific code
  isolated; cross-model matches become cheap later.
- `match/run_match.py` spawns the MCP server subprocess, two harnesses (each with
  their own MCP stdio connection), and the renderer. One process tree.
- **Game scenarios live under `games/<name>/config.yaml`** — terrain + armies +
  starting positions + win rules in one file. Lets us iterate from tiny to
  full-size games and backtest agent behavior across scenarios.
- Replays matter more than expected — watching playback is how you understand why
  one agent is winning.

## Tooling decisions

| Concern | Choice |
|---|---|
| Python version | 3.12 |
| Package manager | `uv` |
| Linter / formatter | `ruff` (both lint + format) |
| Type checker | `pyright` (basic mode), enforced from Phase 1 |
| Test framework | `pytest` |
| MCP library | Official `mcp` Python package |
| Renderer | `rich` (specifically `rich.live.Live`) |
| MCP transport | stdio |
| MCP server lifecycle | One per match |
| Scenario format | YAML (hand-editable) |
| Commit cadence | One commit per phase |

## Phases

### Phase 1 — Game engine (no MCP, no LLM)  *~1-2 days*

Pure Python library where `GameState.apply(action)` works correctly.

- `server/engine/state.py` — dataclasses, dict (de)serialization
- `server/engine/units.py` — class stat tables
- `server/engine/board.py` — grid, BFS pathfinding with terrain costs, attack-range computation
- `server/engine/combat.py` — damage formula, counter, doubling
- `server/engine/rules.py` — `legal_actions`, `apply`, `check_winner`
- `maps/mirror_12x12_basic.json`
- `tests/` — combat math, movement, win conditions

**Demo:** `python -m server.engine.demo` runs a scripted 5-turn game and prints
the board after each turn. Both armies execute hardcoded moves.

### Phase 2 — MCP server  *~1 day*

An MCP server you can poke manually.

- `server/schemas.py` — JSON schemas for every tool
- `server/tools/*.py` — wire each tool to the engine
- `server/main.py` — stdio MCP entrypoint, one `GameState` per process
- `server/engine/replay.py` — log every tool call + state delta to `replays/<game_id>.jsonl`

**Demo:** start server, use `mcp` client to call `get_state`, `move`, `attack`,
`end_turn`. Watch the replay file fill up.

### Phase 3 — Random-agent harness  *~1 day*

Prove the harness loop works without LLM cost or flakiness.

- `harness/harness.py` — the loop, but with a `RandomProvider` instead of an LLM
- `harness/providers/base.py` — provider interface (`generate(messages, tools) -> tool_calls`)
- `harness/providers/random.py` — picks a random legal action via `get_legal_actions`
- `match/run_match.py` — spawns server subprocess + two harnesses, runs to
  completion. **Orchestrator drives turn ordering** (Option C from the design):
  after each `end_turn`, invokes the next harness's `play_turn()` synchronously.
- CLI accepts `--blue` / `--red` model identifiers (special values: `random`).

**Demo:** `python -m match.run_match --blue random --red random --map mirror_12x12_basic`
runs a full game; replay logged; winner declared.

### Phase 4 — Terminal renderer  *~1-2 days*

Watch a match unfold in your terminal in real time.

- `renderer/board_view.py` — ASCII grid: `K` knight, `A` archer, `C` cav, `M` mage; color by team; terrain background
- `renderer/sidebar.py` — active unit stats, last action, turn counter
- Renderer reads from a **spectator stream** (full unfogged state) — separate from agent connections
- Wire renderer into `match/run_match.py`

**Demo:** `match.run_match --render` shows random-vs-random match playing out live.

### Phase 5 — Real LLM harness (single provider)  *~1-2 days*

Claude vs. Claude playing a real game, with optional strategy files.

- `harness/providers/anthropic.py` — wraps Anthropic SDK, converts MCP tool schemas to Anthropic tool format
- `harness/prompts.py` — system prompt explaining game + tool usage philosophy + per-turn template
- `harness/budgets.py` — token/wall-clock enforcement, force `end_turn` on overrun
- `harness/compaction.py` — naive "drop turns older than N" first
- **Strategy file support:** harness loads `--blue-strategy` / `--red-strategy`
  markdown file at startup and pins it into the system prompt. Treated as
  guidance, not law.
- Seed strategies: `strategies/aggressive_rush.md`, `defensive_chokepoint.md`, `balanced.md`.

**Demo:** `match.run_match --blue claude-opus-4-6 --blue-strategy strategies/aggressive_rush.md --red claude-opus-4-6 --red-strategy strategies/defensive_chokepoint.md`
runs a real LLM match where each side has a different playbook. Expect rough
play; this is where you learn what's broken.

### Phase 6 — Coach channel + human input  *~1 day*

Type advice into a sidebar; agent reads it next turn.

- `server/tools/coach.py` — `send_to_agent`, `get_coach_messages` with per-player message queue
- `renderer/coach_input.py` — input box at the bottom; sends to one player's coach channel
- Update harness to call `get_coach_messages` at the start of each turn and inject into prompt

**Demo:** play a Claude-vs-Claude match where you coach blue. Type advice;
observe whether the agent listens.

### Phase 7 — Cross-model matches  *~1 day*

Leaderboard-ready.

- `harness/providers/openai.py`, `gemini.py`, etc.
- `match/run_match.py` accepts arbitrary `--blue` / `--red` model strings
- Optional: `tournament.py` runs N matches, swaps colors, writes win-rate table

**Demo:** `tournament.py --models claude-opus-4-6,gpt-5,gemini-3 --rounds 10`
prints a leaderboard.

### Phase 8 — Polish and stretch  *open-ended*

Decide based on what was learned in phases 5-7.

- Fog of war (server-side filtering, visibility computation)
- More unit classes, terrain, status effects
- Larger / asymmetric maps
- Web renderer for demos
- Replay viewer (`replay.py path/to/replay.jsonl --render`)
- Better compaction (LLM-summarized history vs. just dropping turns)
- Simultaneous turns (Frozen Synapse style)

## Critical-path dependencies

```
Phase 1 (engine) ──┬─→ Phase 2 (MCP) ──→ Phase 3 (random harness) ──┐
                   │                                                 ├─→ 5 (LLM) → 6 (coach) → 7 (multi-model) → 8
                   └─→ Phase 4 (renderer) ──────────────────────────┘
```

Phase 4 only needs the engine + a state stream — can start in parallel with Phase 3.

## Risks / where things get hard

1. **Phase 5 prompt engineering.** Getting an LLM to play *well* (not just legally)
   takes iteration. First match will be bad. Plan for it.
2. **Context management.** A 30-turn match with verbose `get_state` responses
   balloons context. Plan compaction early even if naive.
3. **Coach UX.** Writing-while-watching is hard. The renderer + input box need to
   coexist without flicker. `rich.live.Live` handles this but requires care.
