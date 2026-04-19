"""Input sanitization utilities for untrusted client data."""

from __future__ import annotations

import re

# Matches ANSI escape sequences: ESC [ ... final-byte
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def _strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text)


def _strip_control_chars(text: str, *, allow_newline: bool = False) -> str:
    """Remove characters below 0x20 except space (0x20) and optionally newline."""
    out: list[str] = []
    for ch in text:
        code = ord(ch)
        if code == 0x20:  # space — always keep
            out.append(ch)
        elif allow_newline and ch == "\n":
            out.append(ch)
        elif code < 0x20:
            continue  # strip control char
        else:
            out.append(ch)
    return "".join(out)


def sanitize_display_text(text: str, max_length: int = 64) -> str:
    """Sanitize a short display string (name, model, provider).

    Strips ANSI escapes, control characters (< 0x20 except space),
    leading/trailing whitespace, and truncates to *max_length*.
    """
    text = _strip_ansi(text)
    text = _strip_control_chars(text, allow_newline=False)
    text = text.strip()
    return text[:max_length]


def sanitize_freetext(text: str, max_length: int = 10_000) -> str:
    """Sanitize longer free-form text (thoughts, coach messages).

    Strips ANSI escapes and control characters (except newlines),
    then truncates to *max_length*.
    """
    text = _strip_ansi(text)
    text = _strip_control_chars(text, allow_newline=True)
    return text[:max_length]
