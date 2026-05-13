"""Abstract interface shared by all LLM/VLM providers."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Message:
    role: str  # "user" | "assistant" | "system"
    content: str
    images: list[bytes] = field(default_factory=list)  # raw image bytes for VLM calls


@dataclass
class LLMResponse:
    text: str
    model: str
    raw: Any = None


class LLMProvider(ABC):
    @abstractmethod
    async def chat(self, messages: list[Message], **kwargs: Any) -> LLMResponse: ...

    @abstractmethod
    async def vision(self, prompt: str, image: bytes, **kwargs: Any) -> LLMResponse: ...
