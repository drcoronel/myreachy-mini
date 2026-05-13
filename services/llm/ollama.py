from __future__ import annotations

import base64

import ollama as ollama_client

from core.config import settings

from .base import LLMProvider, LLMResponse, Message


class OllamaProvider(LLMProvider):
    def __init__(self, model: str | None = None) -> None:
        self._model = model or settings.ollama_default_model
        self._client = ollama_client.AsyncClient(host=settings.ollama_host)

    async def chat(self, messages: list[Message], **kwargs) -> LLMResponse:
        formatted = [{"role": m.role, "content": m.content} for m in messages]
        response = await self._client.chat(model=self._model, messages=formatted, **kwargs)
        return LLMResponse(text=response["message"]["content"], model=self._model, raw=response)

    async def vision(self, prompt: str, image: bytes, **kwargs) -> LLMResponse:
        b64 = base64.b64encode(image).decode()
        messages = [{"role": "user", "content": prompt, "images": [b64]}]
        response = await self._client.chat(model=self._model, messages=messages, **kwargs)
        return LLMResponse(text=response["message"]["content"], model=self._model, raw=response)
