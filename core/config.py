from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    reachy_host: str = "reachy-mini.local"
    reachy_port: int = 8000

    google_api_key: str = ""

    ollama_host: str = "http://localhost:11434"
    ollama_default_model: str = "llava:13b"

    dashboard_host: str = "0.0.0.0"
    dashboard_port: int = 8000


settings = Settings()
