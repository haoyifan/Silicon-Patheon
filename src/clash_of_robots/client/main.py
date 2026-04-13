"""`clash-join` CLI entry.

Default mode is the full TUI (login → lobby → room → game → post-match).
The original Phase 1a smoke flow is available under `--smoke` for
testing raw connectivity without driving the TUI.

Usage:
    clash-join                              # interactive TUI
    clash-join --url http://host:8080/mcp/  # preseed the URL field
    clash-join --name alice                 # preseed the display-name field
    clash-join --smoke --name alice         # legacy smoke flow
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from clash_of_robots.client.transport import ServerClient


async def _smoke(
    url: str,
    display_name: str,
    kind: str,
    provider: str | None,
    model: str | None,
) -> int:
    async with ServerClient.connect(url) as client:
        print(f"connected: connection_id={client.connection_id}")
        r = await client.call("whoami")
        print(f"whoami (pre): {json.dumps(r)}")
        r = await client.call(
            "set_player_metadata",
            display_name=display_name,
            kind=kind,
            provider=provider,
            model=model,
        )
        print(f"set_player_metadata: {json.dumps(r)}")
        r = await client.call("heartbeat")
        print(f"heartbeat: {json.dumps(r)}")
        r = await client.call("whoami")
        print(f"whoami (post): {json.dumps(r)}")
    return 0


def _configure_client_logging(display_name_hint: str | None) -> Path:
    """TUI takes over the terminal (screen=True), so logs must go to a
    file instead of stderr or they'd be invisible.

    Each clash-join process gets its own file so two concurrent clients
    never interleave their output. Filename is
      client-<slug>-<pid>-<YYYYMMDDTHHMMSS>.log
    where <slug> comes from the --name flag (if provided) or "anon".
    Returns the chosen path so the caller can print it before the TUI
    takes over the terminal.
    """
    import datetime as _dt
    import logging
    import os
    import re
    from pathlib import Path

    log_dir = Path.home() / ".clash-of-robots" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    slug_src = (display_name_hint or "anon").strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug_src).strip("-") or "anon"
    ts = _dt.datetime.now().strftime("%Y%m%dT%H%M%S")
    log_path = log_dir / f"client-{slug}-{os.getpid()}-{ts}.log"

    handler = logging.FileHandler(log_path, mode="w", encoding="utf-8")
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    )
    root = logging.getLogger()
    # Avoid duplicate handlers if called twice (pytest reruns, etc.).
    if not any(
        getattr(h, "baseFilename", None) == str(log_path) for h in root.handlers
    ):
        root.addHandler(handler)
    root.setLevel(logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("mcp").setLevel(logging.INFO)
    logging.getLogger("clash").info(
        "---- clash-join session started pid=%d log=%s ----", os.getpid(), log_path
    )
    return log_path


def _run_tui(
    url: str | None,
    name: str | None,
    kind: str,
    provider: str | None,
    model: str | None,
    strategy: str | None,
) -> int:
    from pathlib import Path

    from clash_of_robots.client.tui.app import TUIApp
    from clash_of_robots.client.tui.screens.login import LoginScreen
    from clash_of_robots.harness.prompts import load_strategy

    log_path = _configure_client_logging(display_name_hint=name)
    # Print BEFORE the TUI takes the terminal so the user can grep/tail.
    print(f"client log: {log_path}", flush=True)

    app = TUIApp(initial_screen_factory=LoginScreen)
    if url:
        app.state.server_url = url
    if name:
        app.state.display_name = name
    if kind:
        app.state.kind = kind
    if provider:
        app.state.provider = provider
    if model:
        app.state.model = model
    if strategy:
        path = Path(strategy)
        app.state.strategy_path = path
        app.state.strategy_text = load_strategy(path)
    return asyncio.run(app.run())


def main() -> int:
    p = argparse.ArgumentParser(
        description="Connect to clash-serve (TUI by default; --smoke for a connectivity probe)"
    )
    p.add_argument(
        "--url",
        default=None,
        help="MCP streamable-HTTP endpoint (default: http://127.0.0.1:8080/mcp/)",
    )
    p.add_argument("--name", default=None, help="display name")
    p.add_argument("--kind", default="ai", choices=("ai", "human", "hybrid"))
    p.add_argument("--provider", default=None)
    p.add_argument("--model", default=None)
    p.add_argument(
        "--strategy",
        default=None,
        help="path to a STRATEGY.md playbook injected into the agent's system prompt",
    )
    p.add_argument(
        "--smoke",
        action="store_true",
        help="skip the TUI and run a non-interactive connectivity probe",
    )
    args = p.parse_args()

    if args.smoke:
        if not args.name:
            print("--smoke requires --name", file=sys.stderr)
            return 2
        try:
            return asyncio.run(
                _smoke(
                    url=args.url or "http://127.0.0.1:8080/mcp/",
                    display_name=args.name,
                    kind=args.kind,
                    provider=args.provider,
                    model=args.model,
                )
            )
        except (KeyboardInterrupt, SystemExit):
            return 130
        except Exception as e:
            print(f"smoke flow failed: {e}", file=sys.stderr)
            return 1

    try:
        return _run_tui(
            url=args.url,
            name=args.name,
            kind=args.kind,
            provider=args.provider,
            model=args.model,
            strategy=args.strategy,
        )
    except (KeyboardInterrupt, SystemExit):
        return 130
    except Exception as e:
        print(f"TUI error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
