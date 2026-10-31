"""Conversation app: mic → Silero VAD → Whisper STT → Ollama LLM → Kokoro TTS.

Runs the face tracker concurrently so Reachy looks at whoever it's talking to.
Both loops share one robot connection via AppState.

Run against simulator:  REACHY_SIM=1 uv run python -m apps.conversation.main
Run against hardware:   uv run python -m apps.conversation.main
"""

from __future__ import annotations

import asyncio
import logging

from apps.conversation.config import settings
from apps.conversation.personality import load_personality
from core import create_robot
from dashboard.backend.services.face_tracker import run as run_tracker
from dashboard.backend.state import AppState
from services.audio.mic import MicCapture
from services.audio.stt import STTService
from services.audio.tts import TTSService
from services.llm.base import Message
from services.llm.ollama import OllamaProvider

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")


class ConversationApp:
    def __init__(self, state: AppState) -> None:
        self._state = state
        self._personality = load_personality(settings.personality)
        self._mic = MicCapture(
            media_manager=state.robot.media,
            speech_threshold=settings.vad_threshold,
            silence_ms=settings.vad_silence_ms,
        )
        self._stt = STTService(
            model_size=settings.stt_model,
            language=settings.stt_language,
        )
        self._tts = TTSService(voice=settings.tts_voice)
        self._llm = OllamaProvider(model=settings.llm_model)
        self._history: list[Message] = []

    def _build_messages(self, user_text: str) -> list[Message]:
        seeing = self._state.track_mode == "tracking"
        grounding = "You are currently looking at someone." if seeing else "You cannot currently see anyone."
        system_prompt = f"{self._personality} {grounding}"

        return [
            Message(role="system", content=system_prompt),
            *self._history[-6:],
            Message(role="user", content=user_text),
        ]

    async def loop(self) -> None:
        logger.info("Conversation ready — speak to Reachy")
        while True:
            audio = await self._mic.listen()
            if audio.size == 0:
                continue

            user_text = await self._stt.transcribe(audio)
            if not user_text.strip():
                continue

            logger.info("You: %s", user_text)
            messages = self._build_messages(user_text)
            response = await self._llm.chat(messages)
            reply = response.text
            logger.info("Reachy: %s", reply)

            self._history.append(Message(role="user", content=user_text))
            self._history.append(Message(role="assistant", content=reply))

            await self._tts.speak(reply)


async def run() -> None:
    state = AppState()

    with create_robot(sim=settings.sim) as robot:
        state.robot = robot

        logger.info("Waiting for camera stream (WebRTC ~15s)...")
        for i in range(60):
            frame = await asyncio.to_thread(robot.media.get_frame)
            if frame is not None:
                state.robot_ready = True
                h, w = frame.shape[:2]
                logger.info("Camera ready: %dx%d", w, h)
                break
            if i % 10 == 0:
                logger.info("Still waiting... (%ds)", i // 2)
            await asyncio.sleep(0.5)

        if not state.robot_ready:
            logger.warning("Camera unavailable — face tracking disabled")

        robot.wake_up()
        state.tracking = True

        app = ConversationApp(state)
        tasks: list[asyncio.Task] = [asyncio.create_task(app.loop())]
        if state.robot_ready:
            tasks.append(asyncio.create_task(run_tracker(state)))

        try:
            await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            pass
        finally:
            state.tracking = False
            for t in tasks:
                t.cancel()


if __name__ == "__main__":
    asyncio.run(run())
