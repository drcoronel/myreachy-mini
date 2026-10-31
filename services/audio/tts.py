"""Text-to-speech via kokoro (local, expressive, Apple Silicon friendly)."""

from __future__ import annotations

import asyncio
import logging

import numpy as np
import sounddevice as sd

logger = logging.getLogger(__name__)


class TTSService:
    SAMPLE_RATE = 24000

    def __init__(self, voice: str = "af_heart") -> None:
        from kokoro import KPipeline

        self._pipeline = KPipeline(lang_code="a")
        self._voice = voice

    async def speak(self, text: str) -> None:
        logger.info("Synthesizing speech: %r", text)
        audio = await asyncio.to_thread(self._synthesize, text)
        if audio.size:
            logger.info("Playing %.1fs of audio", len(audio) / self.SAMPLE_RATE)
            await asyncio.to_thread(sd.play, audio, self.SAMPLE_RATE)
            await asyncio.to_thread(sd.wait)

    def _synthesize(self, text: str) -> np.ndarray:
        chunks = [audio for _, _, audio in self._pipeline(text, voice=self._voice)]
        return np.concatenate(chunks) if chunks else np.array([], dtype=np.float32)
