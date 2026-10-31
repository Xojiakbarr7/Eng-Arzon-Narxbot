from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import model_validator


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", "../.env"), extra="ignore")
    database_url: str = "sqlite:///./data/catalog.db"
    demo_mode: bool = True
    bot_token: str = ""
    bot_internal_token: str = ""
    admin_token: str = ""
    admin_telegram_ids: str = ""  # Comma-separated Telegram numeric user IDs
    openai_api_key: str = ""  # Private server-only credential for optional OpenAI use
    gemini_api_key: str = ""  # Private server-only credential from Google AI Studio
    ai_provider: str = "gemini"  # gemini (default) or openai
    ai_enabled: bool = False  # No external AI calls without opt-in
    ai_model: str = "gpt-6-luna"  # Used only when AI_PROVIDER=openai
    gemini_model: str = "gemini-2.5-flash-lite"  # Free-tier supported (subject to quotas)
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173,http://localhost:8080"
    init_data_ttl_seconds: int = 3600
    offer_max_age_hours: int = 48
    rate_limit_per_minute: int = 120
    allowed_store_domains: str = "uzum.uz,asaxiy.uz,olcha.uz,texnomart.uz,mediapark.uz"
    app_env: str = "development"

    @model_validator(mode="after")
    def production_safety(self):
        if self.app_env == "production":
            if self.demo_mode:
                raise ValueError("Production uchun DEMO_MODE=false bo‘lishi kerak")
            if not self.bot_token or len(self.admin_token) < 32 or len(self.bot_internal_token) < 32:
                raise ValueError("Production uchun BOT_TOKEN va kamida 32 belgili ADMIN_TOKEN hamda BOT_INTERNAL_TOKEN kerak")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
