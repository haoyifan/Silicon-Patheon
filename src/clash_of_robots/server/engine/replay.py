"""Append-only JSONL replay writer."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class ReplayWriter:
    def __init__(self, path: Path | str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._f = self.path.open("a", buffering=1)

    def write(self, event: dict[str, Any]) -> None:
        self._f.write(json.dumps(event) + "\n")

    def close(self) -> None:
        try:
            self._f.close()
        except Exception:
            pass

    def __enter__(self) -> ReplayWriter:
        return self

    def __exit__(self, *a) -> None:
        self.close()
