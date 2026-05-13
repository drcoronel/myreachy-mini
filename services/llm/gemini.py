from __future__ import annotations

import google.generativeai as genai

from core.config import settings

from .base import LLMProvider, LLMResponse, Message


class GeminiProvider(LLMProvider):
    def __init__(self, model: str = "gemini-2.0-flash-exp") -> None:
        genai.configure(api_key=settings.google_api_key)
        self._model_name = model
        self._model = genai.GenerativeModel(model)

    async def chat(self, messages: list[Message], **kwargs) -> LLMResponse:
        history = [{"role": m.role, "parts": [m.content]} for m in messages]
        response = await self._model.generate_content_async(history, **kwargs)
        return LLMResponse(text=response.text, model=self._model_name, raw=response)

    async def vision(self, prompt: str, image: bytes, **kwargs) -> LLMResponse:
        import PIL.Image
        import io

        img = PIL.Image.open(io.BytesIO(image))
        response = await self._model.generate_content_async([prompt, img], **kwargs)
        return LLMResponse(text=response.text, model=self._model_name, raw=response)
