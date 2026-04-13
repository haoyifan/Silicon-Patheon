"""Post-match scrollable replay viewer.

Reads a run directory's replay.jsonl and renders the interleaved timeline
(agent thoughts, actions, coach messages, errors) through `rich`'s pager
integration. The pager ($PAGER, typically `less`) gives the user native
bidirectional scrolling, search (/), and quit (q) without us having to
implement a raw-mode input loop.

Usage:
    clash-replay runs/20260412T143022_01_tiny_skirmish
    clash-replay --replay path/to/replay.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Iterator

from rich.console import Console
from rich.text import Text


def _iter_events(replay_path: Path) -> Iterator[dict[str, Any]]:
    with replay_path.open("r", encoding="utf-8") as f:
        for i, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                yield {"kind": "malformed", "payload": {"line_no": i, "raw": line}}


def _team_style(team: str | None) -> str:
    if team == "blue":
        return "cyan"
    if team == "red":
        return "red"
    return "white"


def _fmt_event(event: dict[str, Any]) -> Text:
    """Render one replay event as a single Rich Text line."""
    kind = event.get("kind", "?")
    turn = event.get("turn", "?")
    payload = event.get("payload", {}) or {}
    line = Text()
    line.append(f"T{turn:>2} ", style="dim")

    if kind == "agent_thought":
        team = payload.get("team")
        line.append(f"[{team}] ", style=_team_style(team) + " bold")
        line.append("think: ", style="dim")
        line.append(" ".join(str(payload.get("text", "")).split()))
        return line

    if kind == "action":
        # `payload` IS the action result dict — engine writes _record_action.
        action_type = payload.get("type", "action")
        # Determine actor team heuristically.
        actor = payload.get("by") or payload.get("unit_id", "")
        color = _team_style(payload.get("by"))
        line.append(f"[{action_type}] ", style=color + " bold")
        summary = _summarize_action(payload)
        line.append(summary)
        return line

    if kind == "coach_message":
        to = payload.get("to")
        line.append(f"[coach->{to}] ", style="yellow bold")
        line.append(str(payload.get("text", "")))
        return line

    if kind == "agent_error" or kind == "summarize_error":
        team = payload.get("team")
        line.append(f"[{kind} {team}] ", style="red bold")
        line.append(str(payload.get("error", "")))
        return line

    if kind == "forced_end_turn":
        team = payload.get("team")
        line.append(f"[forced_end_turn {team}] ", style="yellow")
        return line

    if kind == "malformed":
        line.append("[malformed] ", style="red")
        line.append(str(payload))
        return line

    # Fallback: render the raw payload.
    line.append(f"[{kind}] ", style="magenta")
    line.append(json.dumps(payload, default=str))
    return line


def _summarize_action(payload: dict[str, Any]) -> str:
    """Short human summary of an action-result dict."""
    t = payload.get("type")
    if t == "move":
        u = payload.get("unit_id")
        frm = payload.get("from") or {}
        to = payload.get("to") or payload.get("dest") or {}
        return f"{u}: ({frm.get('x')},{frm.get('y')}) -> ({to.get('x')},{to.get('y')})"
    if t == "attack":
        return (
            f"{payload.get('unit_id')} -> {payload.get('target_id')} "
            f"(dmg {payload.get('damage_to_defender', '?')}, "
            f"counter {payload.get('counter_damage', '?')})"
        )
    if t == "heal":
        return f"{payload.get('healer_id')} -> {payload.get('target_id')}"
    if t == "wait":
        return str(payload.get("unit_id", ""))
    if t == "end_turn":
        parts = [f"by {payload.get('by')}"]
        if payload.get("winner"):
            parts.append(f"winner={payload.get('winner')}")
        if payload.get("reason"):
            parts.append(f"reason={payload.get('reason')}")
        if payload.get("seized_at"):
            at = payload["seized_at"]
            parts.append(f"at=({at.get('x')},{at.get('y')})")
        return " ".join(parts)
    return json.dumps(payload, default=str)


def view_replay(replay_path: Path, *, use_pager: bool = True) -> int:
    if not replay_path.is_file():
        print(f"replay file not found: {replay_path}", file=sys.stderr)
        return 2

    console = Console()
    ctx = console.pager(styles=True) if use_pager else _Null()
    with ctx:
        console.print(
            Text(f"Replay: {replay_path}", style="bold underline"),
        )
        console.print()
        for event in _iter_events(replay_path):
            console.print(_fmt_event(event))
    return 0


class _Null:
    def __enter__(self) -> "_Null":
        return self

    def __exit__(self, *a: Any) -> None:  # noqa: D401 - context protocol
        pass


def _resolve_replay_path(args: argparse.Namespace) -> Path | None:
    if args.replay is not None:
        return args.replay
    if args.run_dir is not None:
        return args.run_dir / "replay.jsonl"
    return None


def main() -> int:
    p = argparse.ArgumentParser(
        description="Scrollable post-match viewer (timeline of thoughts + actions)."
    )
    p.add_argument(
        "run_dir",
        nargs="?",
        type=Path,
        default=None,
        help="run directory containing replay.jsonl (e.g. runs/20260412T143022_...)",
    )
    p.add_argument(
        "--replay",
        type=Path,
        default=None,
        help="explicit path to replay.jsonl (overrides run_dir)",
    )
    p.add_argument(
        "--no-pager",
        action="store_true",
        help="print directly to stdout instead of piping through $PAGER",
    )
    args = p.parse_args()

    replay_path = _resolve_replay_path(args)
    if replay_path is None:
        p.error("provide a run_dir positional argument or --replay PATH")
        return 2
    return view_replay(replay_path, use_pager=not args.no_pager)


if __name__ == "__main__":
    raise SystemExit(main())
