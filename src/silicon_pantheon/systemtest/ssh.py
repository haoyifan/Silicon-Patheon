"""Thin SSH/SCP wrappers for the system-test framework's remote mode.

Uses ``subprocess`` with the system ``ssh`` and ``scp`` binaries —
no paramiko / fabric dependency. Requires passwordless SSH to the
remote host (operator responsibility).

Every function has a clear timeout; a hung SSH session shouldn't
be able to wedge the orchestrator. Every function returns a
structured result rather than raising — the caller decides how
to react to transient vs terminal failures.
"""

from __future__ import annotations

import logging
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger("silicon.systemtest.ssh")

# SSH options we want on every invocation:
#   - BatchMode=yes: fail immediately if auth would be interactive
#     (no password prompt — we rely on passwordless keys)
#   - StrictHostKeyChecking=accept-new: OK to trust first-seen hosts
#     (avoids "host key verification failed" on first use)
#   - ConnectTimeout=10: fail fast on unreachable hosts
#   - ServerAliveInterval=15 + ServerAliveCountMax=4: drop the SSH
#     session after ~60s of no ack from the remote, so a dead
#     network doesn't hold the orchestrator hostage
_SSH_BASE_OPTS = [
    "-o", "BatchMode=yes",
    "-o", "StrictHostKeyChecking=accept-new",
    "-o", "ConnectTimeout=10",
    "-o", "ServerAliveInterval=15",
    "-o", "ServerAliveCountMax=4",
]


@dataclass
class SshResult:
    """Outcome of a single ssh/scp invocation."""
    ok: bool
    returncode: int
    stdout: str
    stderr: str
    # Shortened command for logging (no secrets — we don't pass any).
    cmd_display: str

    def raise_for_status(self) -> None:
        if not self.ok:
            raise SshError(
                f"ssh command failed (rc={self.returncode}): "
                f"{self.cmd_display}\nstderr:\n{self.stderr[:2000]}"
            )


class SshError(RuntimeError):
    """Raised by ``raise_for_status`` on non-zero ssh/scp exit."""


def run(
    dest: str,
    command: str,
    *,
    timeout_s: float = 30.0,
    stdin: str | None = None,
    check: bool = False,
) -> SshResult:
    """Run a shell command over SSH.

    ``dest`` is an ssh target like ``user@host``. ``command`` is
    passed to the remote shell as a single string (the remote user's
    default shell handles quoting). For complex multi-line scripts,
    pass them via ``stdin`` and use ``command="bash -s"``.

    Returns an :class:`SshResult`. Set ``check=True`` to raise
    :class:`SshError` on non-zero exit.
    """
    cmd = ["ssh", *_SSH_BASE_OPTS, dest, command]
    cmd_display = f"ssh {dest} {command[:100]}{'...' if len(command) > 100 else ''}"
    log.debug("ssh: %s", cmd_display)
    try:
        proc = subprocess.run(
            cmd,
            input=stdin,
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
    except subprocess.TimeoutExpired:
        return SshResult(
            ok=False, returncode=-1,
            stdout="", stderr=f"ssh timeout after {timeout_s}s",
            cmd_display=cmd_display,
        )

    result = SshResult(
        ok=proc.returncode == 0,
        returncode=proc.returncode,
        stdout=proc.stdout,
        stderr=proc.stderr,
        cmd_display=cmd_display,
    )
    if check:
        result.raise_for_status()
    return result


def preflight(dest: str) -> SshResult:
    """Verify passwordless SSH reachability. Non-destructive."""
    return run(dest, "true", timeout_s=15.0)


def scp_pull(
    dest: str,
    remote_path: str,
    local_path: Path,
    *,
    recursive: bool = False,
    timeout_s: float = 120.0,
) -> SshResult:
    """Copy ``remote_path`` from the VPS into ``local_path``.

    Uses the system ``scp``. For directories, pass ``recursive=True``.
    Missing remote files produce a non-zero rc; the caller decides
    whether to treat that as an error (e.g., optional pcap dir may
    not exist if --diagnose-sse wasn't on).
    """
    cmd = ["scp", *_SSH_BASE_OPTS]
    if recursive:
        cmd.append("-r")
    cmd.extend([f"{dest}:{remote_path}", str(local_path)])
    cmd_display = f"scp {dest}:{remote_path} → {local_path}"
    log.debug("scp_pull: %s", cmd_display)
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout_s,
        )
    except subprocess.TimeoutExpired:
        return SshResult(
            ok=False, returncode=-1,
            stdout="", stderr=f"scp timeout after {timeout_s}s",
            cmd_display=cmd_display,
        )
    return SshResult(
        ok=proc.returncode == 0,
        returncode=proc.returncode,
        stdout=proc.stdout,
        stderr=proc.stderr,
        cmd_display=cmd_display,
    )


def quote(s: str) -> str:
    """shlex.quote shorthand — use when injecting a path into a remote shell."""
    return shlex.quote(s)
