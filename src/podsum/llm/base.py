"""The contract every model backend must satisfy.

Kept deliberately tiny. A narrow interface is what makes a component replaceable:
the moment this grows an Ollama-specific argument, the abstraction has failed.

`Protocol` rather than an abstract base class means a backend does not have to
inherit from anything - it just has to have the right methods. Type checking is
structural, which suits plugging in third-party clients.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class LLMClient(Protocol):
    """A text-in, text-out model."""

    @property
    def name(self) -> str:
        """Identifier for logs and cache keys, e.g. `ollama:qwen3:8b`."""
        ...

    def health(self) -> str | None:
        """Return None if usable, otherwise a human-readable reason why not."""
        ...

    def complete(
        self,
        system: str,
        user: str,
        *,
        schema: dict[str, Any] | None = None,
    ) -> str:
        """Run one completion.

        Args:
            system: Instructions about the role and output format.
            user: The actual payload, i.e. the transcript chunk.
            schema: Optional JSON schema. When given, the backend should constrain
                output to valid JSON matching it.

        Returns:
            The raw response text.

        Raises:
            LLMUnavailable: the backend could not be reached.
        """
        ...
