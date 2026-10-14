from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    gemini_api_key: str = ""
    ollama_base_url: str = "http://localhost:11434"
    database_url: str = "sqlite:///./vue.db"
    environment: str = "development"
    voice_stt_model: str = "small.en"
    voice_stt_device: str = "cuda"
    voice_stt_compute_type: str = "int8_float16"
    hardware_tier: str = "unknown"
    ollama_timeout_seconds: int = 180
    ollama_keep_alive: str = "30m"
    # Replace this explicitly in .env before deploying beyond local development.
    jwt_secret: str = "INSECURE-DEV-ONLY-REPLACE-WITH-A-RANDOM-SECRET"

    # Path to the rate-limit config (RPM/TPM/RPD per model)
    rate_limits_path: Path = BASE_DIR / "app" / "llm" / "rate_limits.yaml"


settings = Settings()
