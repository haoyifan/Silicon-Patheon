"""Tests for the provider error classifier."""

from __future__ import annotations

import pytest

from clash_of_odin.client.providers.errors import (
    ProviderError,
    ProviderErrorReason,
    classify,
)


class _FakeHTTPError(Exception):
    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code


def test_401_is_auth() -> None:
    err = classify(_FakeHTTPError(401, "Invalid API key"))
    assert err.reason == ProviderErrorReason.AUTH
    assert err.is_terminal


def test_403_is_auth_permanent() -> None:
    err = classify(_FakeHTTPError(403, "Permission denied"))
    assert err.reason == ProviderErrorReason.AUTH_PERMANENT
    assert err.is_terminal


def test_402_is_billing() -> None:
    err = classify(_FakeHTTPError(402, "insufficient funds"))
    assert err.reason == ProviderErrorReason.BILLING
    assert err.is_terminal


def test_429_is_rate_limit() -> None:
    err = classify(_FakeHTTPError(429, "rate limit exceeded"))
    assert err.reason == ProviderErrorReason.RATE_LIMIT
    assert not err.is_terminal


def test_503_is_overloaded() -> None:
    err = classify(_FakeHTTPError(503, "overloaded"))
    assert err.reason == ProviderErrorReason.OVERLOADED


def test_404_model_not_found() -> None:
    err = classify(_FakeHTTPError(404, "model does not exist"))
    assert err.reason == ProviderErrorReason.MODEL_NOT_FOUND
    assert err.is_terminal


def test_timeout_class_name() -> None:
    class _MyTimeoutError(Exception):
        pass

    err = classify(_MyTimeoutError("socket disconnected"))
    assert err.reason == ProviderErrorReason.TIMEOUT


def test_unknown_exception_caught() -> None:
    err = classify(RuntimeError("something exotic"))
    assert err.reason == ProviderErrorReason.UNKNOWN
    assert not err.is_terminal


def test_provider_error_passes_through_unchanged() -> None:
    original = ProviderError(ProviderErrorReason.BILLING, "out of credit")
    assert classify(original) is original


def test_original_exception_preserved() -> None:
    raw = _FakeHTTPError(429, "slow down")
    err = classify(raw)
    assert err.original is raw
