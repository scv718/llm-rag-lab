from __future__ import annotations

from dataclasses import dataclass

from google import genai
from google.genai import types
from openai import OpenAI


@dataclass(frozen=True)
class LLMSettings:
    provider: str
    model: str
    gemini_api_key: str | None = None
    openai_base_url: str | None = None
    openai_api_key: str | None = None


class LLMProvider:
    def generate_text(self, system_prompt: str, user_prompt: str) -> str:
        raise NotImplementedError


class GeminiProvider(LLMProvider):
    def __init__(self, model: str, api_key: str | None):
        self.model = model
        self.client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(api_version="v1"),
        )

    def generate_text(self, system_prompt: str, user_prompt: str) -> str:
        response = self.client.models.generate_content(
            model=self.model,
            contents=f"[SYSTEM]\n{system_prompt}\n\n[USER]\n{user_prompt}",
        )
        return response.text or ""


class OpenAICompatibleProvider(LLMProvider):
    def __init__(self, model: str, base_url: str | None, api_key: str | None):
        self.model = model
        self.client = OpenAI(
            base_url=base_url,
            api_key=api_key or "dummy",
        )

    def generate_text(self, system_prompt: str, user_prompt: str) -> str:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        return response.choices[0].message.content or ""


def create_llm_provider(settings: LLMSettings) -> LLMProvider:
    provider = (settings.provider or "gemini").strip().lower()

    if provider == "gemini":
        return GeminiProvider(model=settings.model, api_key=settings.gemini_api_key)
    if provider in {"openai", "openai_compatible", "local"}:
        return OpenAICompatibleProvider(
            model=settings.model,
            base_url=settings.openai_base_url,
            api_key=settings.openai_api_key,
        )

    raise ValueError(f"Unsupported LLM provider: {settings.provider}")
