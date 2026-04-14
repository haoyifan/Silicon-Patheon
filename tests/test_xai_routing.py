"""xAI (Grok) provider routing and key resolution."""

from __future__ import annotations

from pathlib import Path

import pytest

from silicon_pantheon.client.agent_bridge import (
    _build_default_adapter,
    _resolve_api_key,
)


@pytest.fixture
def fresh_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Isolate credentials / env so tests don't touch the real home."""
    monkeypatch.setenv("HOME", str(tmp_path))
    # Clear any pre-set provider env vars so key lookup is controlled.
    for var in ("OPENAI_API_KEY", "XAI_API_KEY", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    yield tmp_path


def test_grok_model_prefix_builds_openai_adapter_with_xai_base_url(
    fresh_home, monkeypatch,
):
    """_build_default_adapter('grok-4') should pick xAI, which reuses
    the OpenAI adapter pointed at https://api.x.ai/v1."""
    monkeypatch.setenv("XAI_API_KEY", "sk-xai-test-key")
    adapter = _build_default_adapter("grok-4")
    # Reuses OpenAIAdapter by design — xAI is wire-compatible.
    from silicon_pantheon.client.providers.openai import OpenAIAdapter
    assert isinstance(adapter, OpenAIAdapter)
    # AsyncOpenAI stores base_url on the client.
    assert "api.x.ai" in str(adapter._client.base_url)


def test_resolve_api_key_walks_env_var_for_xai(fresh_home, monkeypatch):
    monkeypatch.setenv("XAI_API_KEY", "env-var-key")
    assert _resolve_api_key("xai") == "env-var-key"


def test_resolve_api_key_returns_none_when_unset(fresh_home):
    assert _resolve_api_key("xai") is None


def test_resolve_api_key_prefers_credentials_file_over_env(
    fresh_home, monkeypatch,
):
    """Credentials-file entries win over env vars. Mirrors the
    OpenAI behavior so either provider feels the same."""
    from silicon_pantheon.client.credentials import (
        Credentials,
        ProviderCredential,
        save,
    )

    monkeypatch.setenv("XAI_API_KEY", "env-key")
    save(
        Credentials(
            default_provider="xai",
            default_model="grok-4",
            providers={
                "xai": ProviderCredential(
                    auth_mode="api_key", inline_key="file-key"
                ),
            },
        )
    )
    assert _resolve_api_key("xai") == "file-key"


def test_grok_without_any_key_raises(fresh_home):
    """No env var, no credentials file entry — the factory raises
    with a message that names the env var to set."""
    with pytest.raises(RuntimeError, match="XAI_API_KEY"):
        _build_default_adapter("grok-3")
