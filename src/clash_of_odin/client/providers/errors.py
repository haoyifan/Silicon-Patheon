"""Provider error classification.

All provider adapter exceptions normalize into `ProviderError` with a
known `reason` so higher layers can decide uniformly between
backoff / retry / concede / escalate-to-user. Reasons mirror
openclaw's classifier, adapted for our smaller feature set.
"""

from __future__ import annotations

from enum import Enum


class ProviderErrorReason(str, Enum):
    # Keys / tokens are wrong or revoked. Force-concede + re-auth.
    AUTH = "auth"
    AUTH_PERMANENT = "auth_permanent"
    # Account has no credit. Force-concede, show banner.
    BILLING = "billing"
    # Temporary — retry with backoff.
    RATE_LIMIT = "rate_limit"
    OVERLOADED = "overloaded"
    TIMEOUT = "timeout"
    # The caller asked for a model the provider doesn't have (removed,
    # renamed, typo in catalog). Prompt the user to pick another.
    MODEL_NOT_FOUND = "model_not_found"
    # The model produced an invalid tool-call payload. Usually
    # unrecoverable within the current turn.
    FORMAT = "format"
    # Session / conversation state expired server-side. Re-open.
    SESSION_EXPIRED = "session_expired"
    # Catch-all.
    UNKNOWN = "unknown"


class ProviderError(RuntimeError):
    """Adapter-raised error with a structured reason + the original
    exception attached for debugging."""

    def __init__(
        self,
        reason: ProviderErrorReason,
        message: str,
        *,
        original: BaseException | None = None,
    ):
        super().__init__(f"{reason.value}: {message}")
        self.reason = reason
        self.original = original

    @property
    def is_terminal(self) -> bool:
        """True when retrying in-place won't help and we should
        concede / re-auth at a higher layer."""
        return self.reason in (
            ProviderErrorReason.AUTH,
            ProviderErrorReason.AUTH_PERMANENT,
            ProviderErrorReason.BILLING,
            ProviderErrorReason.MODEL_NOT_FOUND,
        )


# ---- classifier ----

# Keyword matches against exception type names and message bodies.
# Deliberately simple — openclaw's full classifier is worth it only
# once we have real failure telemetry to guide tuning.


def classify(exc: BaseException) -> ProviderError:
    """Best-effort categorization of an arbitrary SDK exception.

    Returns a ProviderError with the inferred reason and the original
    exception preserved. Callers catch `ProviderError` and route by
    `reason` / `is_terminal`.
    """
    if isinstance(exc, ProviderError):
        return exc

    cls_name = type(exc).__name__.lower()
    msg = str(exc).lower()

    # HTTP status hints — both Anthropic and OpenAI SDKs expose
    # `status_code` on their exception classes.
    status: int | None = getattr(exc, "status_code", None)

    def _mk(reason: ProviderErrorReason, detail: str) -> ProviderError:
        return ProviderError(reason, detail, original=exc)

    if status == 401 or "invalid api key" in msg or "unauthorized" in msg:
        return _mk(ProviderErrorReason.AUTH, "API key rejected or missing")
    if status == 403 or "revoked" in msg or "permission" in msg:
        return _mk(ProviderErrorReason.AUTH_PERMANENT, "key lacks permissions / revoked")
    if status == 402 or "insufficient" in msg or "quota" in msg and "rate" not in msg:
        return _mk(ProviderErrorReason.BILLING, "account out of credit")
    if status == 429 or "rate limit" in msg or "too many" in msg:
        return _mk(ProviderErrorReason.RATE_LIMIT, "rate-limited")
    if status == 503 or "overloaded" in msg or "unavailable" in msg:
        return _mk(ProviderErrorReason.OVERLOADED, "provider overloaded")
    if status == 408 or "timeout" in cls_name or "timed out" in msg:
        return _mk(ProviderErrorReason.TIMEOUT, "request timed out")
    if status == 404 or "model" in msg and ("not found" in msg or "does not exist" in msg):
        return _mk(ProviderErrorReason.MODEL_NOT_FOUND, "model removed or renamed")
    if status == 400 or "invalid" in msg and "argument" in msg:
        return _mk(ProviderErrorReason.FORMAT, "bad request")
    if "session" in msg and "expired" in msg:
        return _mk(ProviderErrorReason.SESSION_EXPIRED, "session expired")
    return _mk(ProviderErrorReason.UNKNOWN, str(exc) or cls_name)
