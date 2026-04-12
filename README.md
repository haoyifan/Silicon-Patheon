# Clash Of Robots

Tactical grid combat (Fire Emblem-ish) played by AI agents. Humans participate
as coaches — they write a `STRATEGY.md`-style playbook and can send live advice
during the match.

See `DESIGN.md` (original motivation), `GAME_DESIGN.md` (full spec), `PLAN.md`
(implementation plan), and `DECISIONS.md` (design-call log).

## Quick start

```bash
uv sync --extra dev
uv run clash-match --game 01_tiny_skirmish --blue random --red random
```

## Layout

- `src/clash_of_robots/server/` — MCP server + game engine
- `src/clash_of_robots/harness/` — agent runner (providers: random, anthropic, openai)
- `src/clash_of_robots/renderer/` — terminal UI
- `src/clash_of_robots/match/` — match orchestrator (CLI entrypoint)
- `games/<name>/config.yaml` — scenario definitions
- `strategies/*.md` — agent playbooks
- `tests/` — pytest suite
