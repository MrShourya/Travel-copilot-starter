from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = "dev"

    openai_api_key: str | None = None
    openai_model: str = "gpt-4.1-mini"

    ollama_model: str = "qwen3:latest"
    ollama_base_url: str = "http://localhost:11434"

    default_model_provider: str = "openai"

    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = None
    langfuse_base_url: str = "http://localhost:3000"


settings = Settings()