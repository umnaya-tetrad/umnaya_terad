from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Настройки сервера. Секреты передаются только переменными окружения."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    polza_api_key: str = Field(default="", repr=False)
    polza_base_url: str = "https://polza.ai/api/v1"
    polza_timeout_seconds: float = Field(default=75, ge=5, le=180)
    polza_connect_timeout_seconds: float = Field(default=10, ge=2, le=30)
    database_url: str = Field(default="", repr=False)
    visitor_cookie_secret: str = Field(default="local-development-only-change-me", repr=False)
    visitor_cookie_secure: bool = False
    trust_forwarded_client_ip: bool = False
    allowed_browser_origins: str = 'https://umnaya-tetrad.ru,https://www.umnaya-tetrad.ru,http://localhost:5173,http://localhost:4173,http://127.0.0.1:5173,http://127.0.0.1:4173'
    network_hourly_sends: int = Field(default=20, ge=3, le=100)
    require_auth_for_analysis: bool = False
    llm_price_verified: bool = False
    auth_session_days: int = Field(default=30, ge=1, le=90)
    daily_free_analyses: int = Field(default=3, ge=1, le=20)
    recurring_daily_free_analyses: int = Field(default=1, ge=1, le=20)
    daily_quota_timezone: str = "Asia/Yekaterinburg"
    quota_reservation_seconds: int = Field(default=240, ge=90, le=900)
    max_image_bytes: int = Field(default=8_000_000, ge=100_000, le=20_000_000)
    max_image_pixels: int = Field(default=36_000_000, ge=1_000_000, le=80_000_000)
    min_image_edge: int = Field(default=240, ge=64, le=2_000)

    @property
    def polza_chat_url(self) -> str:
        return f"{self.polza_base_url.rstrip('/')}/chat/completions"


@lru_cache
def get_settings() -> Settings:
    return Settings()
