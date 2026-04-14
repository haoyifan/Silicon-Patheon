# Game scenarios

Each subdirectory defines one game scenario: terrain, starting armies, win
rules. Loaded at match start by `silicon_pantheon.server.engine.scenarios`.

## Adding a scenario

Create `games/<name>/config.yaml` with this shape:

```yaml
name: Human-readable name
description: What this scenario tests

board:
  width: 12
  height: 12
  terrain:                          # default tile is plain; list only non-plain
    - {x: 3, y: 4, type: forest}    # forest | mountain
  forts:                            # fort tiles (also overrides terrain)
    - {x: 0, y: 0, owner: blue}     # blue | red

armies:
  blue:
    - {class: knight, pos: {x: 0, y: 1}}
    - {class: archer, pos: {x: 1, y: 0}}
  red:
    - {class: knight, pos: {x: 11, y: 10}}

rules:
  max_turns: 30
  fog_of_war: false                 # currently ignored; Phase 8
  first_player: blue
```

Class stats and terrain effects are fixed in
`src/silicon_pantheon/server/engine/units.py` and `state.py`. Scenarios only
define *composition*, not unit rules.
