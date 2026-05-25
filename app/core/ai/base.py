"""Společné typy pro AI providery."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


class AIError(RuntimeError):
    """Obecná chyba při komunikaci s AI providerem."""


class AIRateLimitError(AIError):
    """429 / quota exceeded."""


class AIAuthError(AIError):
    """401 / 403 / špatný API klíč."""


class AINetworkError(AIError):
    """DNS / connection / timeout — kandidát na fallback."""


@runtime_checkable
class AIProvider(Protocol):
    """Minimální kontrakt všech LLM providerů.

    Implementace nesmí blokovat na sítí déle než ~120 s; volá ji QThread worker.
    """

    name: str

    def generate(self, prompt: str, *, system: str | None = None, max_output_tokens: int | None = None) -> str:
        """Vrátí raw text odpověď. Vyhodí AIError podtřídu při selhání."""
        ...

    def health_check(self) -> bool:
        """Rychlé (<2 s) ověření že provider je dosažitelný a autorizovaný."""
        ...
