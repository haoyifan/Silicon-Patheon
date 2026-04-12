# Clash Of Robots

Tactical grid combat (Fire Emblem-ish) played by AI agents. Humans participate
as coaches — they write a `STRATEGY.md`-style playbook and can send live advice
during the match.

See:
- `DESIGN.md` — original motivation
- `GAME_DESIGN.md` — full game spec (units, rules, MCP tool surface, scenarios)
- `PLAN.md` — implementation plan (phases, repo layout, tooling)
- `DECISIONS.md` — log of design calls made during build-out

## Install

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh      # if you don't have uv
uv sync --extra dev
```

Claude (via subscription) is the default LLM and requires the `claude` CLI
(Claude Code) to be installed and logged in. No `ANTHROPIC_API_KEY` needed.

## Run a random-vs-random match

Great for verifying the engine end-to-end:

```bash
uv run clash-match --game 01_tiny_skirmish --blue random --red random --render --seed 42
```

## Run a Claude-vs-Claude match

```bash
uv run clash-match \
  --game 02_basic_mirror \
  --blue claude-sonnet-4-6 --blue-strategy strategies/aggressive_rush.md \
  --red  claude-sonnet-4-6 --red-strategy  strategies/defensive_chokepoint.md \
  --replay replays/my_match.jsonl \
  --render
```

Cost warning: each agent turn takes ~30s and ~15k tokens on Sonnet. A 30-turn
match ≈ 1M tokens of subscription quota. Use `claude-haiku-4-5` for cheaper
development.

## Coach a team during the match

Pass a text file; the orchestrator watches it for new lines between turns.
Append advice while the match runs:

```bash
# Terminal 1
uv run clash-match --game 02_basic_mirror --blue claude-sonnet-4-6 \
  --red claude-sonnet-4-6 --coach-file-blue coach_blue.txt

# Terminal 2 (any time during the match)
echo "push the cavalry on the right flank" >> coach_blue.txt
```

## Run a tournament

```bash
uv run python -m clash_of_robots.match.tournament \
  --game 02_basic_mirror \
  --a claude-sonnet-4-6 \
  --b claude-haiku-4-5 \
  --rounds 6 --cooldown 30
```

Colors swap each round to remove first-player advantage.

## Layout

```
src/clash_of_robots/
├── server/               MCP server + game engine
│   ├── engine/           pure game logic (no MCP)
│   ├── tools/            in-process tool layer (13 tools)
│   ├── session.py        bundles state + coach queues + replay writer
│   └── main.py           FastMCP stdio wrapper (Phase 8-ready)
├── harness/              agent runner
│   ├── providers/        random, anthropic (Claude Agent SDK), openai (stub)
│   └── prompts.py        system prompt + per-turn prompt builders
├── renderer/             terminal UI (rich.Live) + coach file watcher
└── match/                orchestrator: run_match, tournament
games/                    scenario YAMLs (terrain + armies + rules)
strategies/               agent playbooks
tests/                    pytest suite (37 tests)
replays/                  match logs (gitignored)
```

## Status

Phases 0–7 implemented. Tests: 37 passing (engine, tools, match smoke, coach).

Next steps (Phase 8 / open ended):
- MCP server-initiated notifications for remote agents
- Fog of war
- Web renderer
- Replay viewer CLI
- LLM-summarized context compaction
- More scenarios, asymmetric maps, simultaneous turns
