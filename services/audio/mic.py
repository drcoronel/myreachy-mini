"""Microphone capture from robot's onboard mic array with Silero VAD end-of-speech detection.

Uses the SDK's media manager (WebRTC audio stream) instead of a local mic.
The robot's ReSpeaker XVF3800 array provides 16kHz stereo float32 audio via
get_audio_sample(). We downmix to mono and feed 512-sample windows to Silero VAD.
"""

from __future__ import annotations

import asyncio
import logging
import time

import numpy as np

logger = logging.getLogger(__name__)

_SAMPLE_RATE = 16000
_WINDOW_SAMPLES = 512          # Silero VAD requires exactly 512 samples at 16kHz
_SPEECH_THRESHOLD = 0.5
_SILENCE_MS = 1200
_POLL_INTERVAL = 0.01          # seconds between get_audio_sample() calls


class MicCapture:
    def __init__(
        self,
        media_manager: object,
        speech_threshold: float = _SPEECH_THRESHOLD,
        silence_ms: int = _SILENCE_MS,
    ) -> None:
        from silero_vad import load_silero_vad

        self._media = media_manager
        self._model = load_silero_vad()
        self._threshold = speech_threshold
        self._silence_frames = silence_ms // (_WINDOW_SAMPLES * 1000 // _SAMPLE_RATE)

    async def listen(self) -> np.ndarray:
        """Block until a complete utterance is captured. Returns float32 mono array."""
        return await asyncio.to_thread(self._capture_utterance)

    def _capture_utterance(self) -> np.ndarray:
        import torch

        self._media.start_recording()

        buf = np.array([], dtype=np.float32)
        frames: list[np.ndarray] = []
        silence_count = 0
        in_speech = False

        logger.info("Listening...")
        try:
            while True:
                sample = self._media.get_audio_sample()
                if sample is None or len(sample) == 0:
                    time.sleep(_POLL_INTERVAL)
                    continue

                mono = sample.mean(axis=1) if sample.ndim == 2 else sample
                buf = np.concatenate((buf, mono))

                done = False
                while len(buf) >= _WINDOW_SAMPLES:
                    window = buf[:_WINDOW_SAMPLES]
                    buf = buf[_WINDOW_SAMPLES:]

                    prob = float(self._model(torch.from_numpy(window).unsqueeze(0), _SAMPLE_RATE).item())

                    if prob >= self._threshold:
                        if not in_speech:
                            logger.info("Speech detected (vad=%.2f)", prob)
                        in_speech = True
                        silence_count = 0
                        frames.append(window)
                    elif in_speech:
                        frames.append(window)
                        silence_count += 1
                        if silence_count >= self._silence_frames:
                            logger.info("Utterance ended (%d frames)", len(frames))
                            done = True
                            break

                if done:
                    break

        finally:
            self._media.stop_recording()

        return np.concatenate(frames) if frames else np.array([], dtype=np.float32)
