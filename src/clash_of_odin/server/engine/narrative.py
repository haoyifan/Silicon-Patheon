"""Scenario narrative events.

A scenario can declare a `narrative:` block:

    narrative:
      title: "Journey Begins"
      description: "The pilgrims set out toward Thunder Temple."
      intro: "Day 1. The road is long."
      events:
        - {trigger: on_turn_start, turn: 5, text: "Bandits appear..."}
        - {trigger: on_unit_killed, unit_id: u_r_boss, text: "The demon falls."}
        - {trigger: on_plugin, tag: "spawn_wave", text: "Reinforcements!"}

Parsing happens in `build_state` via `parse_narrative(cfg)` and the
result lives on `state._narrative`. The engine calls `fire(state, hook,
**kwargs)` at the right moments; fired events accumulate on
`state._narrative_log` so renderers / replay writers can drain them.

Events fire at most once (keyed by index in the events list).
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class NarrativeEvent:
    trigger: str  # "on_turn_start" | "on_unit_killed" | "on_plugin"
    text: str
    turn: int | None = None
    unit_id: str | None = None
    tag: str | None = None
    # Match-time flag. Not part of the YAML contract.
    fired: bool = False


@dataclass
class Narrative:
    title: str = ""
    description: str = ""
    intro: str = ""
    events: list[NarrativeEvent] = field(default_factory=list)


def parse_narrative(cfg: dict) -> Narrative:
    """Build a Narrative from a scenario YAML dict. Absent fields
    default to empty."""
    block = cfg.get("narrative") or {}
    events: list[NarrativeEvent] = []
    for spec in block.get("events") or []:
        events.append(
            NarrativeEvent(
                trigger=str(spec.get("trigger", "on_turn_start")),
                text=str(spec.get("text", "")),
                turn=spec.get("turn"),
                unit_id=spec.get("unit_id"),
                tag=spec.get("tag"),
            )
        )
    return Narrative(
        title=str(block.get("title", "")),
        description=str(block.get("description", "")),
        intro=str(block.get("intro", "")),
        events=events,
    )


def fire(state, hook: str, **kwargs) -> list[dict]:
    """Fire any matching narrative events; return the list of entries
    emitted (each {text, trigger, ...}).

    Each event fires at most once per match.
    """
    narr: Narrative | None = getattr(state, "_narrative", None)
    if narr is None:
        return []
    emitted: list[dict] = []
    for ev in narr.events:
        if ev.fired:
            continue
        if ev.trigger != hook:
            continue
        if hook == "on_turn_start":
            if ev.turn is not None and int(ev.turn) != int(kwargs.get("turn", -1)):
                continue
        elif hook == "on_unit_killed":
            if ev.unit_id is not None and ev.unit_id != kwargs.get("unit_id"):
                continue
        elif hook == "on_plugin":
            if ev.tag is not None and ev.tag != kwargs.get("tag"):
                continue
        ev.fired = True
        entry = {"trigger": ev.trigger, "text": ev.text}
        if ev.turn is not None:
            entry["turn"] = ev.turn
        if ev.unit_id is not None:
            entry["unit_id"] = ev.unit_id
        if ev.tag is not None:
            entry["tag"] = ev.tag
        emitted.append(entry)
        # Append to state-level log for renderers.
        log = getattr(state, "_narrative_log", None)
        if log is None:
            log = []
            state._narrative_log = log
        log.append(entry)
    return emitted
