"""Tests for the provider / model catalog."""

from __future__ import annotations

from silicon_pantheon.shared.providers import (
    PROVIDERS,
    get_model,
    get_provider,
)


def test_both_core_providers_listed() -> None:
    ids = {p.id for p in PROVIDERS}
    assert "anthropic" in ids
    assert "openai" in ids


def test_every_provider_has_at_least_one_model() -> None:
    for p in PROVIDERS:
        assert p.models, f"provider {p.id} has no models"


def test_every_model_has_positive_context_window() -> None:
    for p in PROVIDERS:
        for m in p.models:
            assert m.context_window > 0, f"{p.id}/{m.id} has zero context window"


def test_get_provider_returns_none_on_unknown() -> None:
    assert get_provider("nonexistent") is None


def test_get_model_roundtrip() -> None:
    m = get_model("anthropic", "claude-sonnet-4-6")
    assert m is not None
    assert m.display_name == "Claude Sonnet 4.6"
    assert get_model("anthropic", "nonexistent") is None
    assert get_model("nonexistent", "claude-sonnet-4-6") is None


def test_api_key_provider_declares_env_var() -> None:
    for p in PROVIDERS:
        if p.auth_mode == "api_key":
            assert p.env_var, f"{p.id} is api_key but no env_var declared"


def test_cost_warning_present() -> None:
    for p in PROVIDERS:
        assert p.token_cost_warning, f"{p.id} missing token_cost_warning"


def test_xai_provider_is_registered_with_grok_models() -> None:
    xai = get_provider("xai")
    assert xai is not None
    assert xai.auth_mode == "api_key"
    assert xai.env_var == "XAI_API_KEY"
    # xAI is OpenAI-compatible — the catalog entry carries the base URL.
    assert xai.openai_compatible_base_url == "https://api.x.ai/v1"
    # At least the flagship + a cheap variant.
    model_ids = {m.id for m in xai.models}
    assert "grok-4" in model_ids
    assert any(m.id.startswith("grok-") for m in xai.models)


def test_grok_model_id_prefix_routes_to_xai_provider() -> None:
    """The agent-bridge factory picks xAI when the model id starts
    with 'grok-'. Here we just validate that the catalog round-trip
    returns the xAI entry for that provider id."""
    m = get_model("xai", "grok-4")
    assert m is not None
    assert m.display_name == "Grok 4"
