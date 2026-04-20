"""Debug-mode invariant checks.

In production, invariant violations (a hidden unit's ID leaking
into a tool response, a hook raising unexpectedly, a plugin
misbehaving) are logged and the process continues. This is the
right call for a live server — one bad scenario shouldn't kill
a whole match.

But during development/debugging, those same violations quietly
bury real bugs. Set ``SILICON_DEBUG=1`` to flip every
invariant check into a crashing assertion: the process raises
``InvariantViolation`` (or exits, for paths that would otherwise
be swallowed too deeply) so the bug surfaces loudly at the
source.

Usage:

    from silicon_pantheon.shared.debug import invariant, is_debug

    invariant(target.alive, f"attacked dead unit {target.id}",
              logger=log)

Under SILICON_DEBUG=1: raises InvariantViolation immediately.
Otherwise: logs ERROR and returns False so callers can skip.

For exception-swallow patterns (``except Exception: pass``) that
want the same behaviour, use ``reraise_in_debug``:

    try:
        hook(session, result)
    except Exception:
        reraise_in_debug(log, "hook raised")
        # falls through in production

This module deliberately has zero dependencies on the rest of
the codebase so it can be imported from anywhere (engine, server,
client, harness) without cycles.
"""

from __future__ import annotations

import logging
import os
from typing import Any


class InvariantViolation(AssertionError):
    """Raised when a debug-mode invariant check fails.

    Subclasses AssertionError so pytest handles it with a clean
    diff diff, and so callers that catch AssertionError in tests
    continue to work. Not caught by the generic
    ``except Exception`` swallowers peppered through the
    codebase — in production those continue to swallow real
    exceptions; in debug mode an InvariantViolation thrown from
    inside such a try/except would still be re-raised because
    ``reraise_in_debug`` is the paired helper (the whole point of
    debug mode is that these DO NOT stay swallowed).
    """


def is_debug() -> bool:
    """True when debug-mode invariant checks should crash.

    Toggled by env var ``SILICON_DEBUG=1``. Read on every call
    so operators can flip the flag live by editing systemd
    environment and restarting (or by exporting before launch
    in dev).
    """
    return os.environ.get("SILICON_DEBUG", "0") == "1"


def invariant(
    condition: bool,
    message: str,
    *,
    logger: logging.Logger | None = None,
    extra: dict[str, Any] | None = None,
) -> bool:
    """Check an invariant. Returns True iff the condition held.

    In debug mode, raises ``InvariantViolation`` if the condition
    is false. In production, logs ERROR with ``message`` and
    ``extra`` and returns False so the caller can decide how to
    continue.

    Prefer specific, actionable messages — these appear in logs
    and in pytest failure diffs during debug runs.
    """
    if condition:
        return True
    _raise_or_log(message, logger=logger, extra=extra)
    return False


def reraise_in_debug(
    logger: logging.Logger | None,
    message: str,
    *,
    extra: dict[str, Any] | None = None,
) -> None:
    """Use inside ``except Exception`` blocks that normally swallow.

    If ``is_debug()``, re-raises the current exception so it
    surfaces at the crash site. Otherwise logs ``logger.exception``
    with ``message`` and returns, matching the legacy swallowing
    behaviour.

    Caller pattern::

        try:
            risky()
        except Exception:
            reraise_in_debug(log, "risky raised")
            # in production, we're still swallowing; in debug
            # mode we never get here (re-raise above)
    """
    if is_debug():
        raise  # re-raise the exception currently being handled
    if logger is not None:
        if extra:
            logger.exception("%s %s", message, extra)
        else:
            logger.exception(message)


def _raise_or_log(
    message: str,
    *,
    logger: logging.Logger | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    if is_debug():
        if extra:
            raise InvariantViolation(f"{message} {extra}")
        raise InvariantViolation(message)
    if logger is not None:
        if extra:
            logger.error("invariant_violation: %s %s", message, extra)
        else:
            logger.error("invariant_violation: %s", message)
