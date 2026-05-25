"""Klient pro lokální Ollama (http://localhost:11434).

Pokud Ollama neběží → AINetworkError, router pak ukáže uživateli návod k instalaci.
"""

from __future__ import annotations

import httpx

from app.config import DEFAULT_OLLAMA_BASE_URL, DEFAULT_OLLAMA_MODEL
from app.core.ai.base import AIError, AINetworkError


class OllamaProvider:
    name = "ollama"

    def __init__(self, base_url: str = DEFAULT_OLLAMA_BASE_URL, model: str = DEFAULT_OLLAMA_MODEL) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model

    def generate(self, prompt: str, *, system: str | None = None, max_output_tokens: int | None = None) -> str:
        url = f"{self._base_url}/api/generate"
        payload: dict = {
            "model": self._model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.3},
        }
        if system:
            payload["system"] = system
        if max_output_tokens:
            payload["options"]["num_predict"] = max_output_tokens

        try:
            response = httpx.post(url, json=payload, timeout=300.0)
        except httpx.RequestError as exc:
            raise AINetworkError(
                "Lokální Ollama není dostupná. Spusť aplikaci Ollama nebo viz docs/INSTALACE_OLLAMA.md."
            ) from exc

        if response.status_code == 404:
            raise AIError(f"Ollama model '{self._model}' není stažený. Spusť `ollama pull {self._model}`.")
        if response.status_code >= 400:
            raise AIError(f"Ollama vrátila chybu {response.status_code}: {response.text[:300]}")

        data = response.json()
        text = data.get("response", "").strip()
        if not text:
            raise AIError("Ollama vrátila prázdnou odpověď")
        return text

    def health_check(self) -> bool:
        try:
            response = httpx.get(f"{self._base_url}/api/tags", timeout=2.0)
            if response.status_code != 200:
                return False
            tags = response.json().get("models", [])
            return any(m.get("name", "").startswith(self._model.split(":")[0]) for m in tags)
        except (httpx.RequestError, ValueError):
            return False
