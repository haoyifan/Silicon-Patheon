"""Provider adapters: one file per LLM provider (anthropic, openai, ...).

Each adapter implements `ProviderAdapter` and is selected at runtime
based on the user's credentials. The rest of the client never imports
provider SDKs directly.
"""

from silicon_pantheon.client.providers.base import (
    ProviderAdapter,
    ThoughtCallback,
    ToolDispatcher,
    ToolSpec,
)

__all__ = ["ProviderAdapter", "ToolSpec", "ThoughtCallback", "ToolDispatcher"]
