"""MCP streamable-HTTP client wrapper.

Wraps the raw mcp SDK client bits into a small async-only API that
matches how our tools look from the caller's perspective: pass a
tool name + kwargs, get back the structured dict the server returned.

All transport errors bubble up as-is so the caller can distinguish
"network said no" from "tool returned {ok: false, error: ...}".
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import secrets
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

log = logging.getLogger("silicon.transport")

CLIENT_HEARTBEAT_INTERVAL_S = 10.0

# Debug gate for the optional per-call / per-heartbeat stall
# diagnostics. Set by ``silicon-host --debug`` / ``silicon-join --debug``
# via SILICON_DEBUG=1. Read once at module import time; callers
# flip the env var before asyncio.run(), so a static read is fine.
_DEBUG = os.environ.get("SILICON_DEBUG") == "1"

# Watchdog + timeout for call_tool inside the lock.
#
# Root cause (confirmed): server restarts kill the SSE connection
# but the MCP SDK doesn't detect the dead streams. call_tool hangs
# forever. The watchdog logs diagnostics every 30s (ws_closed,
# rs_closed, pending_requests) to confirm the streams are dead.
# After CALL_TOOL_TIMEOUT_S, the call is cancelled so the client
# can reconnect instead of hanging indefinitely.
WATCHDOG_INTERVAL_S = 30.0
CALL_TOOL_TIMEOUT_S = 90.0

# Tools that are purely noisy (heartbeat / state polls) are logged at
# DEBUG so the file stays readable; everything else at INFO.
# IMPORTANT: keep get_state at INFO — it's how we see agents / screens
# interact mid-game. We can always tune this down once the stuck-state
# bug is nailed.
_QUIET_TOOLS = frozenset({"heartbeat"})


class RemoteToolError(RuntimeError):
    """Raised when a tool call returned no parseable structured body."""


class ServerClient:
    """Connected MCP client. Use via `ServerClient.connect(url)` as an
    async context manager.

    ── Two MCP sessions, one cid ──
    The client holds **two** MCP sessions to the same server, both
    bound to a single ``connection_id``. ``_session`` carries normal
    tool calls (``get_state``, ``move``, ``end_turn``, …);
    ``_heartbeat_session`` is used exclusively by the heartbeat
    loop. Each session has its own HTTP connection, SSE stream, and
    ``_call_lock``. The MCP SDK's SSE demuxer can't tolerate
    concurrent requests on ONE session (documented below), so the
    lock is non-negotiable per session — but splitting heartbeat
    onto its own session means a 30-second ``get_state`` can't block
    a 10-second heartbeat any more. This directly addresses the
    "silent eviction" failure mode documented in
    ~/dev/heartbeat-resilience-plan.md.
    """

    def __init__(
        self,
        session: ClientSession,
        *,
        heartbeat_session: ClientSession,
        connection_id: str,
    ):
        self._session = session
        self._heartbeat_session = heartbeat_session
        self.connection_id = connection_id
        self._heartbeat_task: asyncio.Task | None = None
        # Serialize all call_tool requests on each session. The MCP
        # SDK demuxes SSE responses by JSON-RPC ID — concurrent
        # requests on ONE session cause responses to get lost /
        # misrouted and one or more call_tool futures hang forever.
        # Even 2 concurrent calls (TUI poll + agent tool) can trigger
        # this. We keep a separate lock per session so the heartbeat
        # session's fast heartbeat calls never wait on the main
        # session's slow tool calls.
        self._call_lock = asyncio.Lock()
        self._heartbeat_call_lock = asyncio.Lock()
        # Layer 1 of transport-resilience (see
        # ~/dev/transport-resilience-plan.md): when the MCP SDK's
        # internal anyio streams go closed (observed as ws_closed=True
        # / rs_closed=True on tool calls after a silent network blip),
        # any in-flight session.call_tool parks forever because
        # nothing wakes the awaiter. This event fires as soon as we
        # detect stream death on EITHER session; the worker's
        # run_forever races its game loop against this event so it
        # can force a full reconnect instead of staying wedged.
        self._transport_dead_event = asyncio.Event()
        self._stream_monitor_task: asyncio.Task | None = None
        self._heartbeat_stream_monitor_task: asyncio.Task | None = None
        # Cached args from the most recent set_player_metadata call,
        # used for auto-recovery when the server has evicted this cid
        # (server returns NOT_REGISTERED; we transparently re-register
        # with the same cid and retry the original call). Populated
        # lazily by ``call()`` itself — callers don't need to plumb it.
        self._last_register_kwargs: dict | None = None

    @classmethod
    @asynccontextmanager
    async def connect(
        cls,
        url: str,
        *,
        connection_id: str | None = None,
    ) -> AsyncIterator["ServerClient"]:
        """Open an MCP+SSE connection to the server and initialize it.

        Yields a ServerClient ready for tool calls.

        ── Instrumentation ──
        Enables DEBUG-level logging on ``httpx`` and ``httpcore`` and
        ``mcp`` so the per-request pool / connection / stream lifecycle
        is visible in the log. This is how we diagnose "hung call_tool
        with no httpx POST log" scenarios — root cause of those is
        usually an httpx pool or connect/write timeout, and the debug
        lines show exactly which phase stalled.

        The log volume is substantial (tens of lines per tool call),
        but these logs are critical for reproducing intermittent
        transport hangs. See docs/THREADING.md for the corresponding
        server-side instrumentation.
        """
        _configure_transport_diagnostics()
        # Start the event-loop stall watchdog under --debug. No-op
        # otherwise. Safe to call multiple times per process; only
        # one watchdog task ever runs.
        from silicon_pantheon.client import diag_loop as _diag_loop
        _diag_loop.start()
        cid = connection_id or secrets.token_hex(8)
        # Strip trailing slash to avoid 307 redirects on every call.
        url = url.rstrip("/")
        log.info(
            "transport connecting: url=%s cid=%s httpx_defaults=%s",
            url, cid, _describe_httpx_defaults(),
        )
        # Two sessions, same server. The first is for tool calls; the
        # second is dedicated to the heartbeat loop. Nested async-with
        # ensures both sessions are torn down cleanly in reverse
        # order if anything inside fails.
        async with streamablehttp_client(url) as (read1, write1, _get_sess_id_1):
            async with ClientSession(read1, write1) as session:
                await session.initialize()
                async with streamablehttp_client(url) as (
                    read2, write2, _get_sess_id_2,
                ):
                    async with ClientSession(read2, write2) as heartbeat_session:
                        await heartbeat_session.initialize()
                        log.info(
                            "transport: both sessions initialized "
                            "(main_sess=%s heartbeat_sess=%s cid=%s)",
                            id(session), id(heartbeat_session), cid,
                        )
                        client = cls(
                            session,
                            heartbeat_session=heartbeat_session,
                            connection_id=cid,
                        )
                        client._start_stream_monitor()
                        try:
                            yield client
                        finally:
                            await client._stop_stream_monitor()

    async def call(self, tool_name: str, **kwargs: Any) -> dict:
        """Call a server tool, returning the structured response dict.

        Uses the main session. Also:

        1. Caches ``set_player_metadata`` args so we can silently
           re-register if the server forgets us later.
        2. Detects the ``not_registered`` error code on the response
           (server evicted us — most likely because an earlier heartbeat
           gap blew through HEARTBEAT_DEAD_S) and transparently
           re-registers with the SAME cid, then retries the original
           call once. This turns a previously fatal "call
           set_player_metadata first" error into a hiccup the caller
           doesn't have to care about.

        Transient transport errors (ClosedResourceError etc.) are
        NOT retried here — a closed stream on the same session can't
        be resurrected by a retry on that same session. Those errors
        trigger ``_transport_dead_event`` which the outer worker races
        against to force a full reconnect.
        """
        # Cache registration args on the way in so we have them later
        # if recovery fires.
        if tool_name == "set_player_metadata":
            self._last_register_kwargs = dict(kwargs)

        result = await self._call_on_session(
            self._session, self._call_lock, tool_name, **kwargs,
        )

        # Auto-recover if the server returned NOT_REGISTERED. We skip
        # the recovery path when the caller IS the set_player_metadata
        # call (would loop) and when we have no cached registration
        # args (nothing to recover to — user must call
        # set_player_metadata themselves first).
        if (
            tool_name != "set_player_metadata"
            and isinstance(result, dict)
            and result.get("ok") is False
            and isinstance(result.get("error"), dict)
            and result["error"].get("code") == "not_registered"
            and self._last_register_kwargs is not None
        ):
            log.warning(
                "call %s returned NOT_REGISTERED for cid=%s — server "
                "forgot us (likely heartbeat-dead eviction). "
                "Re-registering with cached metadata and retrying.",
                tool_name, self.connection_id,
            )
            reregister = await self._call_on_session(
                self._session, self._call_lock,
                "set_player_metadata", **self._last_register_kwargs,
            )
            if not (isinstance(reregister, dict) and reregister.get("ok")):
                log.error(
                    "auto re-register FAILED for cid=%s: %s",
                    self.connection_id, reregister,
                )
                return result  # surface the original error to caller
            log.info(
                "auto re-register succeeded for cid=%s; retrying %s",
                self.connection_id, tool_name,
            )
            result = await self._call_on_session(
                self._session, self._call_lock, tool_name, **kwargs,
            )
        return result

    async def _call_on_session(
        self,
        session: ClientSession,
        lock: asyncio.Lock,
        tool_name: str,
        **kwargs: Any,
    ) -> dict:
        """Generic call-tool wrapper parameterized by which session
        (and matching lock) to use.

        The server always returns JSON wrapped in a TextContent block;
        this helper parses that back out. `connection_id` is injected
        automatically so callers can focus on tool-specific args.
        """
        args = {"connection_id": self.connection_id, **kwargs}
        level = logging.DEBUG if tool_name in _QUIET_TOOLS else logging.INFO
        # Diagnostic identity for the underlying anyio streams. We're
        # chasing a "ClosedResourceError after end_turn" repro: knowing
        # whether the stream object identity changes between calls (vs.
        # the SAME stream object getting closed mid-flight) tells us
        # whether the MCP SDK rotated the session under us, or whether
        # something on the wire / server killed the stream we still
        # hold a reference to.
        import time as _time

        # Acquire the call lock to ensure only one call_tool is in
        # flight at a time on THIS session. The MCP SDK's SSE response
        # demuxer loses responses under concurrent requests on one
        # session, causing permanent hangs. Heartbeat runs on its own
        # session with its own lock so normal tool-call slowness
        # can't starve it.
        async with lock:
            sess_id = id(session)
            ws = getattr(session, "_write_stream", None)
            rs = getattr(session, "_read_stream", None)
            ws_id = id(ws) if ws is not None else None
            rs_id = id(rs) if rs is not None else None
            ws_closed = getattr(ws, "_closed", "?") if ws is not None else "?"
            log.log(
                level,
                "call -> %s cid=%s sess=%s ws=%s ws_closed=%s rs=%s args=%s",
                tool_name, self.connection_id, sess_id, ws_id, ws_closed, rs_id,
                {k: v for k, v in kwargs.items()},
            )
            _t0 = _time.monotonic()
            # Watchdog: periodically log diagnostics if the call is
            # still pending. Does NOT cancel — we want the hang to be
            # visible so we can find the root cause.
            async def _watchdog():
                while True:
                    await asyncio.sleep(WATCHDOG_INTERVAL_S)
                    elapsed = _time.monotonic() - _t0
                    ws2 = getattr(session, "_write_stream", None)
                    rs2 = getattr(session, "_read_stream", None)
                    ws2_closed = getattr(ws2, "_closed", "?") if ws2 is not None else "?"
                    rs2_closed = getattr(rs2, "_closed", "?") if rs2 is not None else "?"
                    # Try to inspect MCP SDK internal state.
                    pending_requests = "?"
                    try:
                        # ClientSession tracks pending requests internally.
                        pending_requests = str(len(getattr(
                            session, "_response_streams", {}
                        )))
                    except Exception:
                        pass
                    log.error(
                        "call HUNG %s cid=%s pending=%.0fs phase=%s — "
                        "ws_closed=%s rs_closed=%s pending_requests=%s "
                        "sess=%s ws=%s rs=%s",
                        tool_name, self.connection_id, elapsed, _phase,
                        ws2_closed, rs2_closed, pending_requests,
                        id(session),
                        id(ws2) if ws2 else None,
                        id(rs2) if rs2 else None,
                    )
            wd_task = asyncio.create_task(_watchdog())
            try:
                # ── Granular diagnostics: instrument the MCP SDK call ──
                # Phase 1: write the request to the SDK's write stream
                # Phase 2: wait for the response from the SSE demuxer
                # This tells us whether the hang is in sending or receiving.
                _phase = "pre-call"
                async def _instrumented_call():
                    nonlocal _phase
                    _phase = "call_tool:entered"
                    log.log(
                        level,
                        "call PHASE %s %s cid=%s",
                        _phase, tool_name, self.connection_id,
                    )
                    # Inspect the write stream state right before we use it
                    _ws = getattr(session, "_write_stream", None)
                    _ws_closed = getattr(_ws, "_closed", "?") if _ws else "?"
                    _req_id = getattr(session, "_request_id", "?")
                    _resp_count = len(getattr(session, "_response_streams", {}))
                    log.log(
                        level,
                        "call PHASE pre-send %s cid=%s req_id=%s "
                        "pending_responses=%s ws_closed=%s",
                        tool_name, self.connection_id,
                        _req_id, _resp_count, _ws_closed,
                    )
                    _phase = "call_tool:sending"
                    result = await session.call_tool(tool_name, args)
                    _phase = "call_tool:done"
                    return result

                result = await asyncio.wait_for(
                    _instrumented_call(),
                    timeout=CALL_TOOL_TIMEOUT_S,
                )
            except asyncio.TimeoutError:
                elapsed = _time.monotonic() - _t0
                ws2 = getattr(session, "_write_stream", None)
                rs2 = getattr(session, "_read_stream", None)
                log.error(
                    "call TIMEOUT %s cid=%s dt=%.1fs phase=%s — "
                    "ws_closed=%s rs_closed=%s.",
                    tool_name, self.connection_id, elapsed, _phase,
                    getattr(ws2, "_closed", "?") if ws2 else "?",
                    getattr(rs2, "_closed", "?") if rs2 else "?",
                )
                raise
            except Exception as e:
                ws2 = getattr(session, "_write_stream", None)
                rs2 = getattr(session, "_read_stream", None)
                log.error(
                    "call !! %s cid=%s exc_type=%s exc=%r dt=%.1fs "
                    "sess_now=%s ws_now=%s ws_closed_now=%s rs_now=%s",
                    tool_name, self.connection_id, type(e).__name__, e,
                    _time.monotonic() - _t0,
                    id(session),
                    id(ws2) if ws2 is not None else None,
                    getattr(ws2, "_closed", "?") if ws2 is not None else "?",
                    id(rs2) if rs2 is not None else None,
                )
                raise
            finally:
                wd_task.cancel()
        _dt = _time.monotonic() - _t0
        if _dt > 5.0:
            log.warning(
                "call SLOW %s cid=%s dt=%.1fs",
                tool_name, self.connection_id, _dt,
            )
        # FastMCP signals tool-level exceptions by returning
        # `isError=True` with a PLAIN-TEXT error message in the text
        # block — NOT JSON. Our envelope always uses {ok, result|error}
        # JSON, so FastMCP's error shape only appears when our handler
        # raised an uncaught exception (e.g. SILICON_DEBUG=1 caught a
        # fog-leak invariant). Detect that case explicitly and raise
        # RemoteToolError so callers get a structured failure, not
        # a `json.loads("Error executing tool ...")` crash.
        is_error = bool(getattr(result, "isError", False))
        for block in result.content:
            text = getattr(block, "text", None)
            if text is None:
                continue
            if is_error:
                # FastMCP error: text is a human-readable string.
                log.error(
                    "call REMOTE_ERROR %s cid=%s dt=%.2fs text=%r",
                    tool_name, self.connection_id, _dt, text[:500],
                )
                raise RemoteToolError(
                    f"tool {tool_name} raised on the server: {text[:300]}"
                )
            # Measure json.loads cost under --debug. A big server
            # response (get_state on a 50-unit scenario, full
            # history, 60k tokens of text) can take tens of ms to
            # decode on a contended laptop — enough to contribute
            # to loop stalls when stacked with other sync work.
            _parse_t0 = _time.monotonic() if _DEBUG else None
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError as e:
                # Non-error payload that isn't JSON — should never
                # happen under our envelope contract. Dump the raw
                # text so we can diagnose. isError was already False.
                log.error(
                    "call JSON_DECODE_ERROR %s cid=%s dt=%.2fs "
                    "text_len=%d text_repr=%r err=%s full_result=%r",
                    tool_name, self.connection_id, _dt,
                    len(text), text[:500], e, result,
                )
                raise RemoteToolError(
                    f"tool {tool_name} returned invalid JSON "
                    f"(len={len(text)}): {text[:200]!r}"
                ) from e
            if _DEBUG:
                _parse_ms = (_time.monotonic() - _parse_t0) * 1000
                # Flag anything that parses slower than a few ms;
                # that's already a meaningful contribution to a
                # stall budget. WARN at > 200 ms since that plus a
                # couple of sibling syncs can blow through 1-2 s
                # of real loop time. DEBUG for everything else so
                # the breakdown is there on demand.
                _lvl = logging.WARNING if _parse_ms > 200 else logging.DEBUG
                log.log(
                    _lvl,
                    "call parse %s cid=%s bytes=%d parse_ms=%.1f",
                    tool_name, self.connection_id,
                    len(text), _parse_ms,
                )
            log.log(
                level,
                "call <- %s ok=%s dt=%.2fs keys=%s",
                tool_name,
                parsed.get("ok"),
                _dt,
                list(parsed.keys())[:8],
            )
            return parsed
        log.error(
            "call NO_TEXT_BLOCK %s cid=%s dt=%.1fs content=%r",
            tool_name, self.connection_id, _dt, result.content,
        )
        raise RemoteToolError(
            f"tool {tool_name} returned no text block: {result!r}"
        )

    # ─── Layer 1 — transport-dead detection ───

    def _start_stream_monitor(self) -> None:
        """Poll the MCP session's anyio streams for silent closure.

        When the SSE transport dies (network blip, proxy close,
        server-side cascade close — any of several causes we've
        chased), the MCP SDK's ``_write_stream`` / ``_read_stream``
        transition to closed locally but nothing wakes existing
        awaiters on them. In-flight ``session.call_tool`` parks
        forever because the future is tied to a stream that will
        never deliver another event.

        This monitor runs as a background task, polls the two
        streams' internal ``_closed`` flag once a second, and fires
        ``_transport_dead_event`` as soon as either goes closed.
        Workers / TUIs race this event against their game-loop task
        so they can force reconnect within ~1 s instead of waiting
        for the 90 s ``wait_for`` timeout that currently catches the
        condition.

        Polling is deliberately used instead of a logging-filter
        hook on ``mcp.client.streamable_http`` because the relevant
        log line ("SSE stream ended: …") is at DEBUG level and
        depends on the caller having bumped that logger; introspection
        of the stream attribute is more robust and self-contained.
        """
        if self._stream_monitor_task is not None and not self._stream_monitor_task.done():
            return

        async def _monitor_one(session: ClientSession, label: str) -> None:
            """Poll one session's streams; fire transport_dead when either goes closed.

            Runs once per session — we have a main session and a
            heartbeat session; either going dead means the transport
            as a whole is dead and a full reconnect is needed, so we
            share the same ``_transport_dead_event``.
            """
            try:
                while not self._transport_dead_event.is_set():
                    await asyncio.sleep(1.0)
                    ws = getattr(session, "_write_stream", None)
                    rs = getattr(session, "_read_stream", None)
                    ws_closed = getattr(ws, "_closed", False) if ws is not None else True
                    rs_closed = getattr(rs, "_closed", False) if rs is not None else True
                    if ws_closed or rs_closed:
                        log.error(
                            "transport DEAD detected (%s session): cid=%s "
                            "ws_closed=%s rs_closed=%s — signalling reconnect",
                            label, self.connection_id, ws_closed, rs_closed,
                        )
                        self._transport_dead_event.set()
                        # Best-effort close of the other side too, so
                        # any awaiter on either stream sees a consistent
                        # ClosedResourceError and unwedges immediately
                        # instead of waiting 90s on wait_for.
                        for stream in (ws, rs):
                            if stream is None:
                                continue
                            try:
                                await stream.aclose()
                            except Exception:
                                pass
                        return
            except asyncio.CancelledError:
                return

        self._stream_monitor_task = asyncio.create_task(
            _monitor_one(self._session, "main"),
        )
        self._heartbeat_stream_monitor_task = asyncio.create_task(
            _monitor_one(self._heartbeat_session, "heartbeat"),
        )

    async def _stop_stream_monitor(self) -> None:
        for attr in ("_stream_monitor_task", "_heartbeat_stream_monitor_task"):
            task = getattr(self, attr, None)
            setattr(self, attr, None)
            if task is None or task.done():
                continue
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    @property
    def transport_dead(self) -> asyncio.Event:
        """Event that fires when the MCP SDK's streams have gone dead.

        Public API for workers / TUIs to race against their main
        loops. Set by ``_start_stream_monitor`` (Layer 1) OR by the
        heartbeat loop after N consecutive ``ClosedResourceError``
        (Layer 2). Cleared by building a fresh ``ServerClient``
        (i.e., reconnecting).
        """
        return self._transport_dead_event

    # ─── heartbeat ───

    async def start_heartbeat(
        self, interval_s: float = CLIENT_HEARTBEAT_INTERVAL_S
    ) -> None:
        """Launch a background task that calls `heartbeat` every N seconds.

        Callers that stay connected for a while (lobby, in-game) should
        start this right after `set_player_metadata` so the server's
        soft-disconnect sweeper doesn't evict them.
        """
        if self._heartbeat_task is not None and not self._heartbeat_task.done():
            return

        # Layer 2 of transport-resilience (see
        # ~/dev/transport-resilience-plan.md). The previous
        # implementation swallowed every exception; when the MCP SDK
        # streams went dead silently, heartbeats emitted
        # ``ClosedResourceError`` every 10s forever with no signal
        # upstream. Now we count consecutive failures and escalate:
        # after MAX_CONSECUTIVE_FAILURES in a row we fire
        # ``_transport_dead_event`` so the outer worker can race
        # against it and force a reconnect, and we stop heartbeating
        # (pointless once the transport is dead).
        #
        # A single transient error still gets swallowed — keep the
        # old tolerance for one-off slow calls / server restarts.
        MAX_CONSECUTIVE_FAILURES = 3
        from anyio import ClosedResourceError

        async def loop() -> None:
            import time as _time
            consecutive_failures = 0
            # Absolute-time scheduling so we can measure how late
            # each wake-up is vs. when it was *supposed* to fire.
            # A drift of more than a couple of seconds is direct
            # evidence the event loop was starved — the mechanism
            # that blows through the server's 45 s heartbeat
            # eviction threshold. Always enabled (very cheap);
            # the warning line only fires under --debug to keep
            # prod logs quiet.
            _next_tick = _time.monotonic() + interval_s
            try:
                while True:
                    _sleep_for = _next_tick - _time.monotonic()
                    await asyncio.sleep(max(0.0, _sleep_for))
                    _lag_s = _time.monotonic() - _next_tick
                    if _DEBUG and _lag_s > 2.0:
                        log.warning(
                            "heartbeat self-lag: wake-up was %.1fs late "
                            "(cid=%s). The previous iteration's "
                            "call_tool took longer than expected — "
                            "either the event loop was blocked (check "
                            "silicon.diag.loop + asyncio slow-callback "
                            "warnings) or the heartbeat session was "
                            "itself slow on the wire. Since this "
                            "heartbeat runs on its OWN session + lock "
                            "as of the 2026-04-23 change, lock-wait "
                            "behind a slow main-session tool call is "
                            "no longer a cause.",
                            _lag_s, self.connection_id,
                        )
                    # Advance the schedule. If we're more than one
                    # interval behind, skip catch-up ticks so a long
                    # stall doesn't produce a burst of back-to-back
                    # heartbeats when the loop recovers.
                    _next_tick += interval_s
                    _now = _time.monotonic()
                    if _next_tick < _now:
                        _skipped = int((_now - _next_tick) / interval_s) + 1
                        if _DEBUG:
                            log.warning(
                                "heartbeat self-lag: skipping %d catch-up "
                                "tick(s) after stall (cid=%s).",
                                _skipped, self.connection_id,
                            )
                        _next_tick = _now + interval_s
                    try:
                        # Use the DEDICATED heartbeat channel so the
                        # main session's slow tool calls can't block
                        # us (see class docstring).
                        await self._call_on_session(
                            self._heartbeat_session,
                            self._heartbeat_call_lock,
                            "heartbeat",
                        )
                        consecutive_failures = 0
                    except ClosedResourceError:
                        consecutive_failures += 1
                        if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                            log.error(
                                "heartbeat: %d consecutive ClosedResourceError "
                                "— transport is dead, signalling reconnect "
                                "(cid=%s)",
                                consecutive_failures, self.connection_id,
                            )
                            self._transport_dead_event.set()
                            return
                    except Exception:
                        # Non-transport errors (RemoteToolError, etc.)
                        # don't indicate a dead transport — keep
                        # heartbeating, but cap iterations so we don't
                        # spin forever if something weird keeps failing.
                        consecutive_failures += 1
                        if consecutive_failures >= 10:
                            log.error(
                                "heartbeat: %d consecutive failures "
                                "(non-Closed) — giving up, reconnecting "
                                "(cid=%s)",
                                consecutive_failures, self.connection_id,
                            )
                            self._transport_dead_event.set()
                            return
            except asyncio.CancelledError:
                return

        self._heartbeat_task = asyncio.create_task(loop())

    async def stop_heartbeat(self) -> None:
        if self._heartbeat_task is not None and not self._heartbeat_task.done():
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
        self._heartbeat_task = None


# ---- transport diagnostics ----

def _configure_transport_diagnostics() -> None:
    """Crank transport loggers to DEBUG so we capture httpx pool +
    connect + write + read lifecycle per request.

    Called once by ``ServerClient.connect``. Idempotent — re-running
    is a no-op because handlers are already attached by the CLI's
    logging setup (which inherits our log file by propagation).
    """
    import logging as _logging
    # We want DEBUG lines from httpx, httpcore, and the MCP SDK
    # itself — they reveal exactly where a hung POST is stalled.
    # Keep uvicorn/asyncio at INFO — those are high-volume and noisy.
    for name in ("httpx", "httpcore", "mcp", "mcp.client.streamable_http"):
        _logging.getLogger(name).setLevel(_logging.DEBUG)


def _describe_httpx_defaults() -> str:
    """Return a short string describing the httpx.Timeout + Limits
    the MCP SDK applies by default. Used in the connect log line so
    operators see what timeouts are in effect.
    """
    try:
        from mcp.shared._httpx_utils import (
            MCP_DEFAULT_SSE_READ_TIMEOUT,
            MCP_DEFAULT_TIMEOUT,
        )
        return (
            f"connect/write/pool={MCP_DEFAULT_TIMEOUT}s "
            f"read={MCP_DEFAULT_SSE_READ_TIMEOUT}s"
        )
    except Exception:  # noqa: BLE001 — diagnostic must never crash
        return "unknown"
