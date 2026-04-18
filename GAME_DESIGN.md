# SiliconPantheon — Game Design

A Fire Emblem-inspired tactics game played by AI agents, with humans participating
as coaches.

## Concept

- **Genre:** turn-based tactical combat on a grid (FE / Advance Wars / Wesnoth lineage).
- **Players:** two AI agents compete head-to-head.
- **Humans:** participate as **coaches** — observe the match and send strategic
  advice to "their" agent between turns. Humans do not directly control units.
- **Interaction:** agents play entirely through an MCP server. The server is the
  authoritative arbiter of game state.

## MVP scope

| Aspect | Choice | Rationale |
|---|---|---|
| Map size | Defined per game scenario | Iterate from tiny to full-size; backtest as we add features |
| Map shape | Mirror, symmetric (for competition) | Fair; asymmetric scenarios allowed via game configs |
| Armies | Defined per game scenario | Iterate from 2 units up to full armies |
| Turns | Alternating (not simultaneous) | Simpler to start; simultaneous is a stretch goal |
| RNG | None (deterministic combat) | Small-sample fairness; can't tell skill from luck otherwise |
| Fog of war | Off | On is a stretch goal; server filters before sending to agent |
| Win condition | Eliminate all enemy units OR seize an enemy fort | Two viable strategies |
| Fort capture | End your turn standing on the enemy fort | FE-style "seize" |
| Draw condition | `max_turns` reached (per scenario) | Prevents stalling |
| First player | Blue; tournament code swaps colors across rounds | Fairness across many games |

## Game scenarios

Rather than hardcoding maps and armies, each game scenario lives in its own
folder under `games/` and contains everything needed to start a match: terrain,
army composition for each side, starting positions, win/draw rules.

```
games/
├── README.md
├── 01_tiny_skirmish/
│   ├── config.yaml
│   └── README.md          # describes the scenario, what it tests
├── 02_basic_mirror/
│   └── config.yaml
└── 03_full_armies/
    └── config.yaml
```

This lets us **start small and iterate**: a 6x6 map with 2 units per side to
validate engine basics, then progressively bigger and more complex scenarios
for backtesting agent behavior as we add features.

Example scenario file:

```yaml
# games/01_tiny_skirmish/config.yaml
name: Tiny Skirmish
description: 6x6, 2 units per side. Smallest possible game; for engine testing.

board:
  width: 6
  height: 6
  terrain:
    # default = plain; only specify non-plain tiles
    - {x: 2, y: 2, type: forest}
    - {x: 3, y: 3, type: forest}
  forts:
    - {x: 0, y: 0, owner: blue}
    - {x: 5, y: 5, owner: red}

armies:
  blue:
    - {class: knight, pos: {x: 0, y: 1}}
    - {class: archer, pos: {x: 1, y: 0}}
  red:
    - {class: knight, pos: {x: 5, y: 4}}
    - {class: archer, pos: {x: 4, y: 5}}

rules:
  max_turns: 20
  fog_of_war: false
  first_player: blue
```

Match invocation references the scenario by folder name:

```bash
python -m match.run_match --game 02_basic_mirror --blue ... --red ...
```

## Core stats

| Stat | Meaning |
|---|---|
| HP | Health, unit dies at 0 |
| ATK | Damage dealt before defense |
| DEF | Subtracted from incoming physical damage |
| RES | Subtracted from incoming magical damage |
| SPD | Determines double-attack threshold |
| RNG | Attack range in tiles (Manhattan), as `[min, max]` |
| MOVE | Movement range per turn |

**Damage formula:** `max(1, ATK - DEF)` for physical, `max(1, ATK - RES)` for magic.
If `attacker.SPD >= defender.SPD + 3`, attacker hits twice.

## Unit classes (MVP)

| Class | HP | ATK | DEF | RES | SPD | RNG | MOVE | Notes |
|---|---|---|---|---|---|---|---|---|
| Knight (melee tank) | 30 | 8 | 7 | 2 | 3 | 1 | 3 | Frontline; soaks physical hits |
| Archer (ranged DPS) | 18 | 9 | 3 | 3 | 5 | 2-3 | 4 | Cannot counter at range 1; glass cannon |
| Cavalry (mobile striker) | 22 | 7 | 4 | 3 | 7 | 1 | 6 | High move, doubles slow units, weak to archers |
| Mage (magic + healer) | 16 | 8 (magic) | 2 | 7 | 4 | 1-2 | 4 | Damage uses RES; can heal adjacent ally for 8 HP instead of attacking |

Rock-paper-scissors: Mage beats Knight, Archer beats Cavalry/Mage, Cavalry beats
Archer (if it reaches), Knight beats Cavalry head-on.

## Terrain (MVP)

| Type | Effect |
|---|---|
| Plain | No effect |
| Forest | +2 DEF; costs 2 to enter; cavalry cannot enter |
| Mountain | +3 DEF, +1 RES; only archers and mages can enter |
| Fort | +3 DEF/RES; heals 3 HP at turn start; capturable for win condition |

## MCP tool surface

### Design principles

1. Server is authoritative — validates every action, rejects illegal ones with a clear reason.
2. Expose legal moves explicitly via `get_legal_actions` — agents shouldn't waste
   tokens re-deriving movement/attack ranges.
3. Atomic actions, not batched turns — agent calls `move` then `attack` then `end_turn`.
4. Read tools are free; write tools advance state.

### Read-only tools

| Tool | Args | Returns |
|---|---|---|
| `get_state` | — | Full visible game state (see schema below) |
| `get_unit` | `unit_id` | Single unit's full stats + status effects |
| `get_legal_actions` | `unit_id` | `{ moves, attacks, heals }` with predicted damage / counters |
| `simulate_attack` | `attacker_id`, `target_id`, `from_tile` | Predicted damage both ways, post-combat HP. **No state change.** |
| `get_threat_map` | `player` | Per-tile, which enemy units could attack a unit standing there next turn (training-wheel; gate behind difficulty) |
| `get_history` | `last_n` | Recent actions + outcomes |
| `get_coach_messages` | `since_turn` | Unread messages from human coach |

### Write tools (only on your turn)

| Tool | Args | Effect |
|---|---|---|
| `move` | `unit_id`, `dest_tile` | Moves unit; unit becomes `moved` (can still attack/heal) |
| `attack` | `unit_id`, `target_id` | Resolves combat from current position; unit becomes `done` |
| `heal` | `healer_id`, `target_id` | Mage heals adjacent ally; counts as the unit's action |
| `wait` | `unit_id` | End unit's turn without acting |
| `undo_last_action` | — | Within current turn, before `end_turn`, only if action did not resolve combat |
| `end_turn` | — | Pass control to opponent; rejects if any unit is mid-action |

### Coach channel

| Tool | Caller | Purpose |
|---|---|---|
| `send_to_agent` | coach | Push advice into the agent's next observation |
| `agent_ask_coach` | agent | Optional: agent requests input with a timeout |

Coach messages queue server-side; agent pulls them via `get_coach_messages` at
turn start. The agent is never interrupted mid-tool-call.

## `get_state` JSON schema

```json
{
  "game_id": "g_8f2a",
  "turn": 7,
  "active_player": "blue",
  "you": "blue",
  "phase": "main",
  "status": "in_progress",
  "winner": null,

  "board": {
    "width": 12,
    "height": 12,
    "terrain": [[{"x": 0, "y": 0, "type": "plain"}, "..."]],
    "forts": [
      {"x": 1, "y": 1, "owner": "blue"},
      {"x": 10, "y": 10, "owner": "red"}
    ]
  },

  "units": [
    {
      "id": "u_b_knight_1",
      "owner": "blue",
      "class": "knight",
      "pos": {"x": 2, "y": 3},
      "hp": 24, "hp_max": 30,
      "atk": 8, "def": 7, "res": 2, "spd": 3,
      "rng": [1, 1], "move": 3,
      "status": "ready",
      "effects": []
    }
  ],

  "turn_clock": {"turns_remaining": 23, "max_turns": 30},
  "last_action": {
    "actor": "u_b_cavalry_1",
    "type": "attack",
    "target": "u_r_knight_1",
    "result": {"damage_dealt": 5, "counter_damage": 3, "killed": false}
  }
}
```

Notes:
- `status` per unit: `ready | moved | done`.
- `phase`: `main | combat | enemy_turn | game_over`.
- Under fog of war, the server filters `units` and `terrain` **before** sending to
  the agent. The agent only ever sees what its side can see. The full unfogged
  state goes to the spectator/renderer over a separate channel.

## Detailed rules

- **Counter-attacks:** defender counters iff the attacker is within the defender's
  `RNG`. Symmetric to attack range. Doubling rule applies on counters too.
- **Healing:** Mage's heal targets an adjacent ally (Manhattan distance 1).
  Cannot self-heal. Counts as the Mage's action for the turn.
- **Stacking:** at most one unit per tile.
- **Action order within a turn:** the player can pick which unit to act with in
  any order. For a given unit, `move` and `attack`/`heal`/`wait` happen
  contiguously (move-then-act). Once a unit is `done`, it cannot act again that
  turn.
- **Fort ownership at start:** each player's home fort is owned by them; any
  mid-map forts start neutral.

## Game flow

```
[Server] start_game(blue_agent, red_agent, map_id, coaches?)
   ↓
[Loop until game_over]
   ↓
[Server] notify active agent: "your turn"
   ↓
[Agent] get_state()                       # observe
[Agent] get_coach_messages(since=turn-1)  # check advice
[Agent] (per unit it wants to act:)
          get_legal_actions(unit_id)
          simulate_attack(...)
          move(unit_id, tile)
          simulate_attack(...)            # re-plan from new position
          attack(unit_id, target_id)
[Agent] end_turn()
   ↓
[Server] resolve, swap active_player
```

- Each turn has a wall-clock budget (e.g. 90s) and a token budget; server
  force-`end_turn`s on overrun.
- Match record (replay) logs every tool call + state delta to a `.jsonl` file.
- Spectator stream is a separate read-only feed pushing full unfogged state to
  the renderer.

### Turn notification

How does an agent know it's its turn?

| Option | Mechanism | Verdict |
|---|---|---|
| A. Polling | Agent calls `get_state` in a loop until `active_player == you` | Wasteful; ugly |
| B. MCP server-initiated notifications | Server pushes a `turn/your_turn` JSON-RPC notification down the active agent's stdio pipe; harness blocks on a notification listener | Correct for remote/long-lived agents |
| C. Orchestrator-driven | `match/run_match.py` already knows whose turn it is; invokes the active harness's `play_turn()` synchronously | Simplest given our architecture |

**Decision:** **Option C** for MVP through Phase 7. The orchestrator owns turn
ordering for logging/budgets anyway, and the harnesses are already in the same
process tree. The idle agent's process simply sits with its stdio connection
open, doing nothing. **Switch to Option B in Phase 8** if/when agents need to
run on different machines or as long-lived services.

Concrete flow:

```python
# match/run_match.py
server = spawn_mcp_server(map_id)
blue = AgentHarness("blue", model_blue, server.stdio_blue, strategy=blue_strategy)
red  = AgentHarness("red",  model_red,  server.stdio_red,  strategy=red_strategy)

while True:
    state = server.get_state_unfiltered()  # orchestrator privilege
    if state["status"] == "game_over":
        break
    active = blue if state["active_player"] == "blue" else red
    active.play_turn()        # blocks until end_turn or budget hits
    renderer.refresh(state)
```

## Specifying agents

For MVP, agents are specified via CLI flags. Each side gets a model ID and an
optional strategy file:

```bash
python -m match.run_match \
  --map mirror_12x12_basic \
  --blue claude-opus-4-6 --blue-strategy strategies/aggressive_rush.md \
  --red  claude-opus-4-6 --red-strategy  strategies/defensive_chokepoint.md \
  --render
```

Built-in special values:
- `--blue random` → `RandomProvider` (Phase 3)
- `--blue human` → human plays via the renderer (stretch goal, not MVP)
- `--blue claude-opus-4-6`, `--blue gpt-5`, etc. → real LLM via that provider

For more complex matches (custom budgets, system prompt overrides, tool gating),
graduate to a YAML config file and pass `--blue agents/aggressive_claude.yaml`:

```yaml
# agents/aggressive_claude.yaml
provider: anthropic
model: claude-opus-4-6
strategy_file: strategies/aggressive_rush.md
budget:
  tokens_per_turn: 20000
  seconds_per_turn: 90
tools:
  threat_map: false      # disable training-wheel tool
```

CLI flags remain a shorthand for the common case.

## Strategy files (`STRATEGY.md`-style playbooks)

Users write a markdown file with strategic guidance ("prioritize archers",
"don't trade knights for cavalry", "control the central forest by turn 5"). The
harness reads it **once at game start** and pins it into the agent's system
prompt.

Why system prompt rather than a tool the agent calls:
- Loaded once → fits prompt cache → cheap across all turns.
- Always present in reasoning context, not "out of sight" until called.
- Agent doesn't waste tokens deciding whether to consult it.

Recommended directory layout:

```
strategies/
├── aggressive_rush.md           # rush enemy fort, accept losses
├── defensive_chokepoint.md      # hold forest tiles, attrition
├── balanced.md
└── README.md                    # how to write a strategy file
```

Recommended sections inside a strategy file (suggested, not enforced):
- **Doctrine** — high-level posture (aggressive / defensive / opportunistic)
- **Unit priorities** — how to use each class, what to protect, what to sacrifice
- **Target priorities** — what enemy units to kill first
- **Map heuristics** — which terrain to control
- **Endgame** — when to switch from attrition to fort-capture

The agent treats the strategy file as **guidance, not law** — final tactical
decisions still come from `get_state` reasoning. The system prompt makes this
explicit: *"The strategy file is your captain's intent; deviate when the
tactical situation demands it."*

Strategy files become first-class once Phase 5 (real LLM harness) lands.
Different strategy files paired with the same model is one of the most
interesting axes for the eventual leaderboard.

## Architecture

- **One MCP server per match** (start simple; long-lived multi-match server is a
  stretch goal).
- **Transport:** stdio.
- **Renderer:** terminal first (`rich.live.Live`); web later.
- **Harness:** one harness instance per agent, each with its own stdio
  connection, conversation history, and budget. Agents identified by connection.

### Agent harness solutions

| Option | Pros | Cons |
|---|---|---|
| Anthropic SDK + built-in MCP client | Least code | Claude-only; needs API key |
| Claude Agent SDK | Loop, compaction, subagents free; reuses Claude Code auth | Claude-only |
| Roll-your-own (`mcp` client + provider SDKs) | Per-agent model choice; cross-model matches | ~300 lines to write |
| LangGraph / LlamaIndex | — | Overkill |

**Plan:** **Claude Agent SDK** for Phases 5-6, reusing the user's existing Claude
Max subscription auth (no separate API key needed). Add provider-specific
clients (OpenAI, etc.) in Phase 7 only for the non-Claude side of cross-model
matches.

### Authentication

| Side | Auth source | Setup |
|---|---|---|
| Claude (any model) | Existing Claude Max subscription via Claude Agent SDK | None — same login as Claude Code |
| OpenAI / GPT | `OPENAI_API_KEY` env var | Phase 7 only |
| Google / Gemini | `GOOGLE_API_KEY` env var | Phase 7 only |
| `random`, `human` | None | — |

**Subscription rate limits matter.** A 30-turn match with both sides on Opus is
60+ model calls; back-to-back tournaments will hit Max limits. Mitigations:
- Use `claude-sonnet-4-6` or `claude-haiku-4-5` during development; reserve
  `claude-opus-4-6` for real matches.
- Keep per-turn token budgets tight (e.g. 20k).
- Add inter-match cooldowns in the tournament orchestrator (Phase 7).
