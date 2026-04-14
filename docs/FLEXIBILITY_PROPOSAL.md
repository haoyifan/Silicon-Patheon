# Design: multi-provider agents + flexible scenarios

Final design for the two big feature asks. Reflects the decisions made
in the 2026-04-13 review.

Status: **approved, not yet implemented**. See [TODO.md](../TODO.md) for
deferred items.

---

# Feature 1 — Multi-provider agent support

## Scope

**v1 ships Anthropic + OpenAI only.** Gemini, Ollama, and the others
are in `TODO.md`. Each player picks their own provider + model
independently; the server never touches LLM code.

The game operator may decide, e.g. in tournament settings, to
pre-verify model choices out-of-band. The backend doesn't enforce it.

## Provider catalog (`shared/providers.py`)

Declarative, hand-maintained:

```python
@dataclass(frozen=True)
class ModelSpec:
    id: str                          # e.g. "claude-sonnet-4-6"
    display_name: str
    context_window: int
    supports_tools: bool             # v1 filters out anything that doesn't
    cost_per_mtok_in: float | None   # informational only
    cost_per_mtok_out: float | None

@dataclass(frozen=True)
class ProviderSpec:
    id: str                          # "anthropic" | "openai"
    display_name: str
    auth_mode: Literal["api_key", "subscription_cli"]
    env_var: str | None              # "ANTHROPIC_API_KEY" | "OPENAI_API_KEY"
    keyring_service: str             # "clash-of-odin-<provider>"
    models: list[ModelSpec]
    token_cost_warning: str          # shown on the login-screen picker
```

## Authentication flow

New TUI screen `ProviderAuthScreen` between login and lobby. On
**first run** with no credentials stored:

1. **Provider picker** (button list): "Anthropic (Claude CLI subscription)",
   "OpenAI (API key)". Warning banner at bottom: *"This game burns tokens.
   Make sure your account has budget — running out mid-match auto-concedes
   that match."*
2. **Auth step** — forks by `auth_mode`:
   - `api_key`: check env var → if set, offer to use it ("found
     `OPENAI_API_KEY` in env — use?"); otherwise prompt for paste,
     offer to store in OS keyring via `python-keyring`. **Never**
     stores the key inline in the credentials file; records only a
     ref.
   - `subscription_cli`: shell out to `which claude` and `claude --version`;
     if missing, print install instructions and refuse to continue;
     if present, confirm.
3. **Model picker** — list the provider's models with cost hints.

On **subsequent runs**: skip straight to a one-line "Using Anthropic
/ claude-sonnet-4-6 — [Enter] continue, [c] change" prompt.

## Credential storage

```
~/.clash-of-odin/credentials.json    (0600)
```

```json
{
  "default_provider": "anthropic",
  "default_model": "claude-sonnet-4-6",
  "providers": {
    "anthropic": {"auth_mode": "subscription_cli"},
    "openai":    {"auth_mode": "api_key", "key_ref": "keyring:clash-of-odin-openai/default"}
  }
}
```

**Secret material stays in env vars or the OS keyring.** `key_ref`
values accepted:

- `"env:VAR_NAME"` — read `os.environ[VAR_NAME]` at call time.
- `"keyring:<service>/<username>"` — call `keyring.get_password(...)`.

Secrets never live in the JSON file. If `python-keyring` isn't
installed, we only offer env-var mode and tell the user how to
install it.

## Tool-use adapter

Common interface (in `client/providers/base.py`):

```python
class ProviderAdapter(Protocol):
    async def play_turn(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        tools: list[ToolSpec],
        tool_dispatcher: Callable[[str, dict], Awaitable[dict]],
        on_thought: Callable[[str], Awaitable[None]] | None,
    ) -> None: ...

    async def summarize_match(self, ...) -> Lesson | None: ...

    async def close(self) -> None: ...
```

One concrete file per provider:

- `client/providers/anthropic.py` — wraps `claude-agent-sdk`'s
  `ClaudeSDKClient`. Essentially today's `NetworkedAgent`, extracted.
- `client/providers/openai.py` — uses the official OpenAI Python SDK's
  Responses API with function calling. Session persistence via the
  Conversations API (OpenAI's equivalent to Anthropic's persistent
  client).

`NetworkedAgent` becomes a thin orchestrator that composes the right
adapter from the credentials file.

## Error classification (copied from openclaw)

Exceptions bubble up as `ProviderError(reason=...)`:

| reason | HTTP | action |
|---|---|---|
| `auth` / `auth_permanent` | 401 / 403 | kick back to provider-auth screen; force concede the current match |
| `rate_limit` | 429 | exponential backoff, show banner; retry within time budget |
| `billing` | 402 | show "out of credit — auto-conceding" banner, then concede |
| `overloaded` | 503 | jittered retry up to N times |
| `model_not_found` | 404 | show "model X was removed, pick another"; return to provider-auth screen |
| `timeout` | 408 | retry once |
| `format` | 400 | log + force concede (model produced invalid tool args, unrecoverable in this turn) |
| `unknown` | — | log full traceback, retry once |

**Mid-match auth failure behavior** is **force-concede** (already
agreed). The login-screen warning sets that expectation up front.

## Phasing for Feature 1

- **Phase 1a** — extract `ProviderAdapter` protocol; port current Anthropic
  code behind it. Zero behavior change.
- **Phase 1b** — add `ProviderAuthScreen` + credentials store +
  keyring integration.
- **Phase 1c** — add OpenAI adapter.
- **Phase 1d** — error classifier + force-concede wiring.

After this lands, everything else (Gemini, Ollama, etc.) is "add
another adapter file" — see TODO.md.

---

# Feature 2 — Flexible scenarios

## Scope decisions

Shipped in v1:
- Custom unit classes
- Custom terrain types (with generic effect hooks — see below)
- Declarative win conditions (DSL)
- Plugin-rules escape hatch (operator-curated)
- Scripted narrative (intro text + per-turn events)
- Schema versioning + client/server handshake
- **Reserved fields** for inventory, MP, abilities, tags, damage types
  (v1 schema, v1 engine treats them as no-ops with sane defaults)
- *Journey to the West* as the flagship shipped scenario

**Not shipped in v1** (reserved in schema, deferred in TODO.md):
- Inventory + trading mechanics
- MP + skills + abilities
- Damage types / tag-based resistance / weapon triangle
- Treasure terrain / consumable pickups

## Schema versioning & client/server handshake

### Scenario schema

Every scenario YAML gains a top-level:

```yaml
schema_version: 1
```

Scenarios missing the field are treated as v1. When the engine loads
a scenario with a `schema_version` higher than it understands, it
refuses to register the scenario and logs which version is needed.

### Protocol handshake

`set_player_metadata` already exists; we add a `protocol_version` to
its response. Client sends its supported version on connect; server
compares:

- **Client version < server version** → server refuses with
  `ErrorCode.VERSION_MISMATCH` + a message like `"client v3 not
  supported by server v5; upgrade clash-of-odin to ≥5"`.
- **Client version > server version** → server also refuses, same
  code, `"client v5 talking to server v3; downgrade or wait for
  server upgrade"`.

No best-effort compat: **hard refuse** is the right policy per the
review. We tag `PROTOCOL_VERSION = 1` in `shared/protocol.py` and
bump it only when wire compatibility breaks.

## Unit classes (v1 shipping)

Per-scenario YAML block that adds or overrides classes:

```yaml
unit_classes:
  monkey_king:
    # Core v1 stats.
    hp_max: 45
    atk: 16
    defense: 5
    res: 5
    spd: 11
    rng_min: 1
    rng_max: 2
    move: 8
    sight: 6
    is_magic: false
    can_enter_forest: true
    can_enter_mountain: true
    can_heal: false
    heal_amount: 0

    # v1 reserved fields — see "Reserved fields" below.
    tags: [flying, divine]
    mp_max: 0
    mp_per_turn: 0
    abilities: []
    default_inventory: []
    damage_profile: {}      # empty = use legacy ATK-DEF/RES formula
    defense_profile: {}
```

The built-in four classes stay as documented defaults in
`engine/units.py`. Scenario YAML can override them for that scenario
only (e.g. a "high-damage Knight" variant without changing the
default).

## Terrain types (v1 shipping)

Generic effect hooks modeled on the win-condition plugin system:

```yaml
terrain_types:
  sand:
    glyph: "~"
    color: yellow
    passable: true
    move_cost: 2
    defense_bonus: 0
    magic_bonus: 0
    heals: 0                      # negative = damage
    blocks_sight: false
    class_overrides:
      cavalry: {passable: false}

  # v1 shipping: declarative effects above cover 80%. For anything
  # weirder, point at a plugin callable:
  cursed_swamp:
    glyph: "s"
    passable: true
    effects_plugin: "rules.py:cursed_swamp_effect"
```

`effects_plugin` is a `module:function` reference inside the
scenario's directory. Called on turn-end and on-enter with
`(state, unit, tile)`; may mutate unit HP/status. **Operator-
curated, not sandboxed** — trust model is "if it's registered on the
server, the operator vouched for it." This matches the win-condition
plugin story.

Built-in types (`plain`, `forest`, `mountain`, `fort`) stay
first-class; scenario YAML can override them per-scenario.

## Win conditions (v1 shipping)

Rule list evaluated at well-defined engine hooks. Stock types
cover common cases; plugin escape hatch for anything else.

Stock types (each a Python class in `engine/win_conditions/`):

| type | trigger | meaning |
|---|---|---|
| `seize_enemy_fort` | `end_turn` | your unit on an enemy-owned fort → you win |
| `eliminate_all_enemy_units` | `end_turn` | opponent has no alive units → you win |
| `max_turns_draw` | `end_turn` | turn > N → draw |
| `protect_unit` | `on_unit_killed` | if listed unit dies, its team loses |
| `reach_tile` | `on_action_applied` | unit X on tile Y → win |
| `hold_tile` | `end_turn` | unit on tile Y for N consecutive turns → win |
| `reach_goal_line` | `on_action_applied` | unit on x=V or y=V → win |
| `plugin` | varies | `module:function` escape hatch |

Ordering: rules evaluated in YAML order at the trigger point; **first
match wins**. Scenario YAML documents the precedence (e.g. for
*Journey to the West*, `protect_unit` comes first so Tang Monk dying
ends the match immediately, even if you seized something on the same
turn).

## Scripted narrative (v1 shipping)

Scenarios can provide:

```yaml
narrative:
  title: "Journey to the West"
  description: |
    Pilgrimage to India. Blue (four pilgrims) must reach the Temple
    of Lingshan while Red (ten monsters) tries to capture Tang Monk.

  intro: |                      # displayed at match start
    Tang Monk: "The road is long but the scripture awaits."

  events:
    - trigger: {type: turn_start, turn: 5}
      text: "Clouds gather in the west — something stirs."
    - trigger: {type: unit_killed, unit_id: u_r_white_bone_demon_1}
      text: "The White Bone Demon vanishes in a shriek of dust."
    - trigger: {type: plugin, module: "rules.py:reinforcement_check"}
      text: "Reinforcements arrive from the north."
      plugin: "rules.py:spawn_reinforcements"
```

Text-only events are a no-op when the field is absent. Default
narrative (when no `narrative:` block exists) = just the scenario's
`name`.

Plugin events can mutate state (`spawn_reinforcements` adds units);
this is the mechanism for scripted reinforcements, terrain changes,
etc. Same operator-trust model.

## Reserved fields for future features

The schema includes the following fields from v1 even though v1
engine treats them as no-ops. This means *Journey to the West* can
ship with rich unit definitions now, and later upgrades don't break
existing scenarios.

### Inventory (future)

```yaml
items:                            # scenario-local item catalog
  iron_staff:
    type: weapon
    tags: [staff, divine]
    attack_bonus: 3
  peach_of_immortality:
    type: consumable
    heals: 20
    uses: 1

unit_classes:
  monkey_king:
    default_inventory: [iron_staff, peach_of_immortality]
    ...
```

v1 engine: records inventory on the unit, doesn't act on it.
v2 engine: `trade_item`, `use_item` tools, effects on combat.

### MP / abilities (future)

```yaml
abilities:                        # scenario-local ability catalog
  fire_bolt:
    description: "Magic attack, range 2-3, ignores DEF."
    mp_cost: 10
    damage_type: fire
    rng_min: 2
    rng_max: 3
    target: enemy
    damage_formula: "atk + 5"

unit_classes:
  mage:
    mp_max: 30
    mp_per_turn: 0                # default: no recharge
    abilities: [fire_bolt, ...]
```

v1 engine: stores `mp_max` + `mp_per_turn` on the Unit, no `use_ability`
tool, abilities list ignored.
v2 engine: new MCP tool `use_ability(ability_id, target)`; MP
resource management; recharge per unit's `mp_per_turn` at end_turn.
**Default recharge = 0** (set explicitly so it's discoverable).

### Damage types / tags / weapon triangle (future)

Generalize the current `ATK - DEF` (or `ATK - RES` for magic) into a
tag-aware matrix. Still covers the classic weapon triangle as a
special case.

```yaml
unit_classes:
  archer:
    tags: [ranged, piercing]
    damage_profile: {physical: 9}   # attacks deal 9 physical damage
    defense_profile: {physical: 3, magic: 3}
    # Bonus vs. tagged targets (weapon-triangle as a special case):
    bonus_vs_tags:
      - {tag: flying, mult: 2.0}    # Fire Emblem-style "bows shoot flyers"

  pegasus_knight:
    tags: [flying, armored]
    damage_profile: {physical: 10}
    defense_profile: {physical: 6, magic: 2}
    vulnerability_to_tags:
      - {tag: piercing, mult: 2.0}
```

v1 engine: uses legacy `ATK - DEF` when `damage_profile` / `defense_profile`
are empty (default). Ignores tags, `bonus_vs_tags`, etc.

v2 engine: if `damage_profile` is present, use it; resolve tag
bonuses against `bonus_vs_tags` and defender's
`vulnerability_to_tags`; fall back to legacy formula only for
scenarios that don't opt in.

**Backward compatibility**: existing 4-class stats map cleanly
(`{physical: atk}` / `{physical: defense, magic: res}`) so v1
scenarios continue to compute identical damage numbers under v2.

### Weapon triangle (as a special case)

Declared in the scenario or in a shared catalog:

```yaml
tag_cycles:
  - tags: [sword, axe, spear, sword]     # cyclic; each beats the next
    advantage_mult: 1.15                  # 15% damage bonus (FE classic)
```

Interpreted by the v2 damage resolver as a shortcut for writing
out `bonus_vs_tags` on every weapon individually.

## Journey to the West — flagship acceptance test

The scenario uses everything v1 actually ships (custom classes,
custom terrain, declarative win conditions, narrative events) plus
the reserved future-fields on the units so the v2 upgrade can flip
on richer combat without re-authoring. Concrete sketch:

```yaml
schema_version: 1
name: "Journey to the West"
description: "Pilgrimage to India against ten demons."

unit_classes:
  sun_wukong:
    hp_max: 45
    atk: 16
    defense: 5
    spd: 11
    move: 8
    rng_min: 1
    rng_max: 2
    sight: 6
    is_magic: false
    can_enter_forest: true
    can_enter_mountain: true
    can_heal: false
    # Future-ready:
    tags: [flying, divine]
    mp_max: 40
    abilities: [seventy_two_transformations, cloud_somersault]
    default_inventory: [ruyi_jingu_bang]

  zhu_bajie:
    hp_max: 42
    atk: 13
    defense: 9
    spd: 5
    move: 4
    rng_min: 1
    rng_max: 1
    sight: 3
    can_enter_forest: true
    can_enter_mountain: false
    can_heal: false
    tags: [gluttonous]
    mp_max: 10

  sha_wujing:
    hp_max: 38
    atk: 11
    defense: 7
    spd: 6
    move: 4
    rng_min: 1
    rng_max: 1
    sight: 4
    can_enter_forest: true
    can_enter_mountain: true
    can_heal: false
    tags: [loyal]

  tang_monk:
    hp_max: 18
    atk: 0
    defense: 2
    spd: 3
    move: 3
    rng_min: 0
    rng_max: 0
    sight: 3
    can_enter_forest: true
    can_enter_mountain: false
    can_heal: true
    heal_amount: 10
    tags: [noncombatant, vip]

  white_bone_demon:
    hp_max: 30
    atk: 13
    defense: 4
    res: 6
    spd: 8
    move: 5
    rng_min: 1
    rng_max: 2
    sight: 5
    is_magic: true
    tags: [shapeshifter, undead]
    # Divine units punch through this:
    vulnerability_to_tags:
      - {tag: divine, mult: 1.5}

  bull_demon_king:
    hp_max: 55
    atk: 16
    defense: 10
    res: 3
    spd: 4
    move: 5
    rng_min: 1
    rng_max: 1
    sight: 3
    tags: [armored, earth]

  # ... eight more monster classes

items:
  ruyi_jingu_bang:
    type: weapon
    tags: [staff, divine]
    attack_bonus: 2

terrain_types:
  mountain_pass:
    glyph: "^"
    move_cost: 3
    defense_bonus: 3
    blocks_sight: true
  river:
    glyph: "~"
    passable: false
    class_overrides:
      sun_wukong: {passable: true}      # he flies
  temple:
    glyph: "T"
    defense_bonus: 5
    heals: 5                            # standing here recovers 5 HP per turn

board:
  width: 15
  height: 10
  terrain:
    - {x: 7, y: 0, type: river}
    - {x: 7, y: 1, type: river}
    # ... river bisects map
    - {x: 14, y: 5, type: temple}       # goal
  forts:
    - {x: 0, y: 5, owner: blue}

armies:
  blue:
    - {class: tang_monk,  pos: {x: 0, y: 5}}
    - {class: sun_wukong, pos: {x: 0, y: 4}}
    - {class: zhu_bajie,  pos: {x: 0, y: 6}}
    - {class: sha_wujing, pos: {x: 1, y: 5}}
  red:
    - {class: white_bone_demon, pos: {x: 7, y: 3}}
    - {class: bull_demon_king,  pos: {x: 10, y: 5}}
    # ... eight more

narrative:
  intro: |
    Four pilgrims must reach the Temple of Lingshan.
    Ten demons stand in their way.
  events:
    - trigger: {type: turn_start, turn: 5}
      text: "Clouds gather — the path ahead grows dark."

win_conditions:
  - type: protect_unit          # if Tang Monk dies, Blue loses
    unit_id: u_b_tang_monk_1
    owning_team: blue
  - type: reach_tile             # if Tang Monk reaches temple, Blue wins
    team: blue
    unit_id: u_b_tang_monk_1
    pos: {x: 14, y: 5}
  - type: eliminate_all_enemy_units
    trigger: end_turn
  - type: max_turns_draw
    turns: 40

rules:
  schema_version: 1
  first_player: red              # monsters move first
  fog_of_war: classic
```

Running this under the v1 engine ignores the reserved fields —
`tags` / `mp_max` / `abilities` / `vulnerability_to_tags` / `default_inventory`
— and plays as pure stat-based combat. The scenario file doesn't
change when v2 ships; the engine flips a switch and the tags start
mattering.

## Client-side full preview

The lobby preview today shows map + units. Extended design: the
server exposes a new `describe_scenario(scenario)` tool that returns
**everything a client needs to preview and explain**:

```json
{
  "schema_version": 1,
  "narrative": {"title": "...", "description": "...", "intro": "..."},
  "unit_classes": { "sun_wukong": {...}, ... },
  "terrain_types": { "river": {...}, ... },
  "items": { "ruyi_jingu_bang": {...}, ... },
  "abilities": { "fire_bolt": {...}, ... },
  "win_conditions": [{"type": "protect_unit", "unit_id": "..."}, ...],
  "armies": {"blue": [...], "red": [...]},
  "board": {"width": 15, "height": 10, "terrain": [...], "forts": [...]}
}
```

Client caches this on join and renders tooltips in the room screen
("Hover a unit glyph in the preview → see its stats + tags +
abilities"). This is a client-side v2 TUI enhancement; v1 client can
ignore the extra fields gracefully.

Backend tool signature is v1, but the fields are forward-compatible —
v2 client gets richer tooltips; v1 client gets what it does today.

## Phasing for Feature 2

- **Phase 2a** — schema_version + protocol handshake + custom unit
  classes. Smallest useful slice. Start authoring *Journey to the West*
  immediately with v1 4-class combat math.
- **Phase 2b** — custom terrain types with declarative effects; built-in
  four still the defaults.
- **Phase 2c** — declarative win conditions, replacing hardcoded
  seize/eliminate/max_turns with a rule list. Built-in rule list =
  what's hardcoded today.
- **Phase 2d** — plugin rules + plugin terrain effects + scripted
  narrative events. Operator-curated, no sandbox.
- **Phase 2e** — `describe_scenario` tool + client tooltips on preview.
- **Ship *Journey to the West*** scenario at end of Phase 2d.

v2 engine work (inventory, MP, tags in combat, weapon triangle) is
[TODO](../TODO.md) — the schema hooks ship in v1 but the runtime
doesn't act on them yet.

---

# Operator trust model

- **Scenario registry is operator-controlled.** Clients can't upload
  scenarios — they pick from whatever the server has in `games/`.
- **Plugins (`rules.py` per scenario) run in-process, no sandbox.**
  Acceptable because the operator already reviews what's in the repo.
- **Document this clearly** in `docs/USAGE.md`: *"Scenarios may ship
  with Python code that runs on your server. Only register scenarios
  from authors you trust."*
- **Future marketplace** (where users submit scenarios for review) is
  out of scope — a PR workflow into the operator's git repo is the
  current submission mechanism.

---

# Risks

- **Provider tool-use drift**: Anthropic MCP and OpenAI function
  calling diverge on schema quirks. Budget a solid day per adapter
  beyond the first, plus end-to-end testing that the game actually
  completes with each provider.
- **Persistent sessions**: Anthropic and OpenAI both support them
  (SDKClient / Conversations API). For future providers we'd re-send
  the transcript each turn — fine but more expensive.
- **Schema bloat in `get_state`**: 30-unit *Journey to the West* with
  tags + full unit profiles grows the turn prompt substantially.
  Consider a `get_compact_state` variant once real scenarios show
  where the fat is. Not a Phase 2 blocker.
- **Win-condition ordering bugs**: documented precedence by YAML
  order + tests per scenario per ordering assumption.
- **Keyring package availability**: `python-keyring` has real-world
  quirks on Linux (backend detection, unlocked session requirement).
  Env-var fallback is essential.
- **Fragmented user runs**: scenario list changes, keys change,
  credential file format changes — version-gate the credentials
  file shape too (`credentials.json` gets its own `version` field;
  migrate silently on read, error on read of newer versions).

---

# Acceptance criteria

Feature is "done" when:

**Feature 1 (multi-provider)**
- [ ] `clash-join` on a fresh machine with no env vars drops into the
      provider picker, lets the user paste an OpenAI key into the
      OS keyring, and successfully plays a match against an Anthropic
      opponent.
- [ ] Revoking the OpenAI key mid-match triggers a graceful
      force-concede with the opponent declared winner.
- [ ] Second run skips straight to the lobby ("Using openai /
      gpt-5 — Enter to continue").
- [ ] `TODO.md` documents the remaining providers and a rough
      effort estimate for each.

**Feature 2 (flexible scenarios)**
- [ ] Two clients play *Journey to the West* end-to-end with the
      shipped schema. Tang Monk is protectable and can reach the
      temple; at least one win-condition type from each DSL option
      (`protect_unit`, `reach_tile`, `eliminate_all_enemy_units`,
      `max_turns_draw`) fires in observed matches.
- [ ] A scenario with a `rules.py` plugin callable runs without
      crashing; a scenario with a missing plugin function errors
      cleanly at registration time, not mid-match.
- [ ] `schema_version: 2` YAML refuses to load on v1 engine with a
      clear error listing the supported version.
- [ ] A v0 client (no version sent) refuses to connect to a v1
      server with a clear "upgrade" message.
- [ ] Reserved fields (`tags`, `abilities`, `mp_max`,
      `default_inventory`, `damage_profile`) round-trip through the
      YAML loader, land on the Unit objects, and are returned by
      `get_state` — even though the engine doesn't act on them yet.

---

# Recommended sequencing

Suggest implementing in this order (each item is a landable PR/commit):

1. `schema_version` + protocol handshake (foundation; trivial but
   unblocks everything else)
2. Custom unit classes (Phase 2a)
3. Refactor `NetworkedAgent` → `ProviderAdapter` (Phase 1a)
4. `ProviderAuthScreen` + credentials store + keyring (Phase 1b)
5. OpenAI adapter (Phase 1c)
6. Error classifier + force-concede (Phase 1d)
7. Custom terrain types (Phase 2b)
8. Declarative win conditions (Phase 2c)
9. Plugin rules + scripted narrative (Phase 2d)
10. Ship *Journey to the West*
11. `describe_scenario` + client tooltips (Phase 2e)

Steps 1–6 unblock multi-provider play. Steps 7–11 unblock
scenario authorship. No single step is larger than a day of focused
work.
