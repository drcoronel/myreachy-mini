from pydantic_settings import BaseSettings, SettingsConfigDict


class ConversationSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="CONV_",
        extra="ignore",
    )

    # LLM
    llm_model: str = "llama3.2:3b"

    # STT
    stt_model: str = "large-v3-turbo"
    stt_language: str = "en"

    # TTS
    tts_voice: str = "af_heart"

    # Mic / VAD
    vad_threshold: float = 0.5
    vad_silence_ms: int = 1200

    # Personality
    personality: str = "friendly"

    # Simulator
    sim: bool = False


settings = ConversationSettings()
