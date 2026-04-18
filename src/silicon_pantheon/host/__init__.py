"""Automated bot host — keeps N game rooms available for visitors.

This package is architecturally separate from the client TUI and the
server.  It is a standalone automation layer that uses the same MCP
transport and agent bridge as the TUI, but orchestrates the room
lifecycle programmatically.

    silicon-host config.toml

See ``config.py`` for the TOML schema and ``runner.py`` for the
worker lifecycle.
"""
