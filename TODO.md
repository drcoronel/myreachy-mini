# TODO

## Done
- [x] `_build_messages()` — conversation context window with personality + grounding
- [x] Personality system — `config/personalities.yaml` + `load_personality()` loader
- [x] Silero VAD — replace RMS energy threshold in `MicCapture`
- [x] STT upgrade — faster-whisper `large-v3-turbo`, pinned `language="en"`
- [x] Simulator support — `create_robot(sim=True)`, `CONV_SIM` env var
- [x] Conversation config — pydantic-settings `ConversationSettings` with `CONV_` prefix
- [x] Robot mic array — `MicCapture` now uses SDK `media.get_audio_sample()` over WebRTC
- [x] pydantic-settings `extra="ignore"` — both `Settings` and `ConversationSettings`
- [x] README.md — architecture diagram, apps/services docs, quick start

---

## Dashboard integration

The conversation app imports the face tracker from `dashboard.backend.services` but doesn't
integrate with the dashboard UI. These changes would unify them:

- [ ] Add conversation status panel to dashboard frontend (listening / transcribing / thinking / speaking)
- [ ] Expose conversation state in `AppState` (current utterance, last reply, pipeline stage)
- [ ] Add start/stop conversation endpoint to dashboard backend (`/api/ai/conversation/`)
- [ ] Show live transcript in dashboard (user + Reachy messages)
- [ ] Personality switcher in dashboard UI (dropdown from `config/personalities.yaml`)
- [ ] Decouple face tracker from `dashboard.backend.services` — move to `services/vision/` so both dashboard and conversation app import from the same place without the circular dependency

---

## Next: Agentic capabilities via smolagents CodeAgent

**Goal:** Give Reachy the ability to perform actions mid-conversation (web search, API calls)
using smolagents `CodeAgent` backed by a local Ollama model.

### Plan

1. **Pull the model**
   ```
   ollama pull qwen2.5-coder:14b
   ```
   Update `CONV_LLM_MODEL=qwen2.5-coder:14b` in `.env`.

2. **Create `services/agent/agent.py`**
   - `ReachyAgent` wraps a smolagents `CodeAgent`
   - Ollama connected via `OpenAIServerModel` (Ollama's OpenAI-compatible endpoint)
   - Start with two tools: `DuckDuckGoSearchTool`, `VisitWebpageTool` (no API keys needed)
   - Exposes a single `async def run(user_text: str) -> str` method

3. **Wire into `ConversationApp`**
   - Replace `self._llm.chat()` with `self._agent.run(user_text)`
   - Use `asyncio.to_thread` — smolagents is synchronous

4. **Handle latency in the voice loop**
   - While the agent is running, Reachy should say *"let me think about that"* or wiggle antennas
   - Add a `thinking` state to `AppState` so the face tracker can react

5. **Add `CONV_AGENT_ENABLED` flag to config**
   - `false` by default — falls back to plain `OllamaProvider` for fast replies
   - `true` enables full CodeAgent with tools
