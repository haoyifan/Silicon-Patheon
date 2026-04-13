"""`clash-serve` CLI entry — MCP over streamable HTTP.

Separate module from `server/main.py` (which hosts the legacy stdio
MCP server for `clash-match` in-process use) so the two do not
conflict during the Phase 1 transition.

Usage:
    clash-serve                      # listen on 127.0.0.1:8080
    clash-serve --host 0.0.0.0 --port 9000
"""

from __future__ import annotations

import argparse
import datetime as _dt
import logging
import os
from pathlib import Path

from clash_of_robots.server.app import App, build_mcp_server


def _configure_server_logging(level: str, log_file: Path | None) -> Path:
    """Install a stderr + optional file handler on the root logger.

    If `log_file` is None, a default path is picked under
    ~/.clash-of-robots/logs/server-<pid>-<timestamp>.log so every run
    produces its own file without clobbering the previous one.
    Returns the chosen file path.
    """
    if log_file is None:
        log_dir = Path.home() / ".clash-of-robots" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        ts = _dt.datetime.now().strftime("%Y%m%dT%H%M%S")
        log_file = log_dir / f"server-{os.getpid()}-{ts}.log"
    else:
        log_file.parent.mkdir(parents=True, exist_ok=True)

    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    root = logging.getLogger()
    root.setLevel(getattr(logging, level))

    # stderr handler — same visual experience as before.
    stream = logging.StreamHandler()
    stream.setFormatter(fmt)
    root.addHandler(stream)

    # File handler for archived / shareable logs.
    fh = logging.FileHandler(log_file, mode="w", encoding="utf-8")
    fh.setFormatter(fmt)
    root.addHandler(fh)
    return log_file


def main() -> int:
    p = argparse.ArgumentParser(description="Run the clash-of-robots backend")
    p.add_argument("--host", default="127.0.0.1", help="bind address (default: 127.0.0.1)")
    p.add_argument("--port", type=int, default=8080, help="bind port (default: 8080)")
    p.add_argument(
        "--log-level",
        default="INFO",
        choices=("DEBUG", "INFO", "WARNING", "ERROR"),
        help="server log level",
    )
    p.add_argument(
        "--log-file",
        type=Path,
        default=None,
        help=(
            "path for the server log file. Defaults to "
            "~/.clash-of-robots/logs/server-<pid>-<timestamp>.log"
        ),
    )
    args = p.parse_args()

    log_file = _configure_server_logging(args.log_level, args.log_file)
    log = logging.getLogger("clash-serve")
    log.info("server log file: %s", log_file)
    # Keep a single stderr line identical to the old UX for quick discovery.
    print(f"server log: {log_file}", flush=True)

    app = App()
    mcp = build_mcp_server(app)

    # FastMCP owns the Starlette app + uvicorn lifecycle; it reads host/port
    # from its settings object.
    mcp.settings.host = args.host
    mcp.settings.port = args.port

    log.info("clash-serve starting on http://%s:%d", args.host, args.port)

    # Launch the heartbeat sweeper as a background task on the same
    # asyncio loop FastMCP will use. We do this via a one-off anyio
    # shim so it runs for the lifetime of mcp.run().
    import anyio

    from clash_of_robots.server.heartbeat import run_sweep_loop

    async def _serve() -> None:
        async with anyio.create_task_group() as tg:
            tg.start_soon(run_sweep_loop, app)
            tg.start_soon(mcp.run_streamable_http_async)

    anyio.run(_serve)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
