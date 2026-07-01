"""Speech-to-text via faster-whisper (local, CPU-friendly)."""

from __future__ import annotations

import asyncio
import logging

import numpy as np

logger = logging.getLogger(__name__)


class STTService:
    def __init__(self, model_size: str = "large-v3-turbo", language: str = "en") -> None:
        from faster_whisper import WhisperModel

        self._model = WhisperModel(model_size, device="cpu", compute_type="int8")
        self._language = language

    async def transcribe(self, audio: np.ndarray, sample_rate: int = 16000) -> str:
        def _run() -> str:
            logger.info("Transcribing %.1fs of audio...", len(audio) / sample_rate)
            segments, info = self._model.transcribe(
                audio,
                language=self._language,
                beam_size=5,
                vad_filter=False,      # Silero VAD already handled upstream
                condition_on_previous_text=True,  # improves coherence across segments
            )
            text = " ".join(s.text.strip() for s in segments)
            logger.info("Transcribed (lang=%s, prob=%.2f): %r", info.language, info.language_probability, text)
            return text

        return await asyncio.to_thread(_run)
