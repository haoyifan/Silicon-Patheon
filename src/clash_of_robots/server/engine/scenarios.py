"""Load game scenarios from games/<name>/config.yaml into a GameState."""

from __future__ import annotations

import uuid
from pathlib import Path

import yaml

from .state import (
    Board,
    GameState,
    Pos,
    Team,
    TerrainType,
    Tile,
    Unit,
    UnitClass,
    UnitStatus,
)
from .units import make_stats


def _games_root() -> Path:
    """Find the repo-level games/ directory.

    Walks up from this file until it finds a sibling `games/` folder.
    """
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "games"
        if candidate.is_dir():
            return candidate
    raise FileNotFoundError("Could not locate games/ directory")


def load_scenario(name: str) -> GameState:
    """Load a scenario by folder name (e.g. '01_tiny_skirmish')."""
    config_path = _games_root() / name / "config.yaml"
    if not config_path.exists():
        raise FileNotFoundError(f"No scenario at {config_path}")
    with config_path.open() as f:
        cfg = yaml.safe_load(f)
    return build_state(cfg)


def build_state(cfg: dict) -> GameState:
    board_cfg = cfg["board"]
    width = int(board_cfg["width"])
    height = int(board_cfg["height"])
    tiles: dict[Pos, Tile] = {}

    for t in board_cfg.get("terrain", []) or []:
        pos = Pos(int(t["x"]), int(t["y"]))
        tiles[pos] = Tile(pos=pos, type=TerrainType(t["type"]))

    # Forts overlay: they become FORT tiles with a fort_owner.
    for f in board_cfg.get("forts", []) or []:
        pos = Pos(int(f["x"]), int(f["y"]))
        tiles[pos] = Tile(pos=pos, type=TerrainType.FORT, fort_owner=Team(f["owner"]))

    board = Board(width=width, height=height, tiles=tiles)

    units: dict[str, Unit] = {}
    for team_name in ("blue", "red"):
        team = Team(team_name)
        for idx, u in enumerate(cfg["armies"].get(team_name, []), start=1):
            cls = UnitClass(u["class"])
            stats = make_stats(cls)
            pos = Pos(int(u["pos"]["x"]), int(u["pos"]["y"]))
            uid = f"u_{team.value[0]}_{cls.value}_{idx}"
            units[uid] = Unit(
                id=uid,
                owner=team,
                class_=cls,
                pos=pos,
                hp=stats.hp_max,
                status=UnitStatus.READY,
                stats=stats,
            )

    rules = cfg.get("rules", {})
    max_turns = int(rules.get("max_turns", 30))
    first_player = Team(rules.get("first_player", "blue"))

    return GameState(
        game_id=f"g_{uuid.uuid4().hex[:8]}",
        turn=1,
        max_turns=max_turns,
        active_player=first_player,
        first_player=first_player,
        board=board,
        units=units,
    )
