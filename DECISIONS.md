# Decisions Log

Running log of design and implementation calls made by Claude during build-out
of Clash Of Robots. Each entry: what was decided, why, and any reversal cost if
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
**Decision:** Project named "Clash Of Robots", Python package `clash_of_robots`,
Python 3.12, `uv` for env management, `ruff` for lint+format, `pyright` (basic
mode) for type checking enforced from Phase 1, `pytest` for tests, src layout
(`src/clash_of_robots/...`).
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
