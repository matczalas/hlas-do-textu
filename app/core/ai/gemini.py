"""Klient pro Google Gemini přes nový `google-genai` SDK.

Importuje se line — některé prostředí ho nemusí mít k dispozici (offline-only setup).
"""

from __future__ import annotations

from app.config import DEFAULT_GEMINI_MODEL
from app.core.ai.base import AIAuthError, AIError, AINetworkError, AIRateLimitError


class GeminiProvider:
    name = "gemini"

    def __init__(self, api_key: str, model: str = DEFAULT_GEMINI_MODEL) -> None:
        if not api_key or not api_key.strip():
            raise AIAuthError("Chybí API klíč pro Gemini")
        self._api_key = api_key
        self._model = model
        self._client = None

    def _get_client(self):
        if self._client is not None:
            return self._client
        try:
            from google import genai
        except ImportError as exc:
            raise AIError(
                "Knihovna google-genai není nainstalovaná. Spusť `pip install google-genai`."
            ) from exc
        self._client = genai.Client(api_key=self._api_key)
        return self._client

    def generate(self, prompt: str, *, system: str | None = None, max_output_tokens: int | None = None) -> str:
        client = self._get_client()
        try:
            from google.genai import types as genai_types
        except ImportError as exc:
            raise AIError("google-genai nemá očekávané typy") from exc

        config_kwargs: dict = {}
        if system:
            config_kwargs["system_instruction"] = system
        if max_output_tokens:
            config_kwargs["max_output_tokens"] = max_output_tokens

        config = genai_types.GenerateContentConfig(**config_kwargs) if config_kwargs else None

        try:
            response = client.models.generate_content(
                model=self._model,
                contents=prompt,
                config=config,
            )
        except Exception as exc:  # noqa: BLE001 — SDK chyby mají vlastní hierarchii
            self._reraise_as_ai_error(exc)

        text = getattr(response, "text", None)
        if not text:
            raise AIError("Gemini vrátil prázdnou odpověď")
        return text

    def health_check(self) -> bool:
        try:
            self.generate("Odpověz jen 'OK'.", max_output_tokens=10)
            return True
        except AIError:
            return False

    @staticmethod
    def _reraise_as_ai_error(exc: Exception) -> None:
        message = str(exc).lower()
        if any(k in message for k in ("api key", "unauthorized", "permission", "401", "403")):
            raise AIAuthError(f"Gemini: neplatný API klíč ({exc})") from exc
        if any(k in message for k in ("quota", "rate", "429", "resource_exhausted")):
            raise AIRateLimitError(f"Gemini: vyčerpaný limit ({exc})") from exc
        if any(k in message for k in ("connect", "timeout", "network", "dns", "ssl")):
            raise AINetworkError(f"Gemini: síťová chyba ({exc})") from exc
        raise AIError(f"Gemini: {exc}") from exc
