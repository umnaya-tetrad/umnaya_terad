from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Настройки сервера. Секреты передаются только переменными окружения."""

    model_config = SettingsConfigDict(extra="ignore")

    polza_api_key: str = Field(default="", repr=False)
    polza_base_url: str = "https://polza.ai/api/v1"
    polza_timeout_seconds: float = Field(default=300, ge=5, le=300)
    polza_connect_timeout_seconds: float = Field(default=15, ge=2, le=30)
    pilot_transport: str = "polza"
    pilot_storage_root: str = "/data/pilot/photos"
    polza_model: str = "google/gemini-3.8-flash"
    polza_provider: str = "google-ai-studio/flex"
    polza_max_completion_tokens: int = 25000
    polza_max_price_prompt: float = 50
    polza_max_price_completion: float = 250
    polza_max_price_image: float = 50
    database_url: str = Field(default="", repr=False)
    visitor_cookie_secret: str = Field(default="local-development-only-change-me", repr=False)
    visitor_cookie_secure: bool = False
    trust_forwarded_client_ip: bool = False
    allowed_browser_origins: str = 'https://umnaya-tetrad.ru,https://www.umnaya-tetrad.ru,http://localhost:5173,http://localhost:4173,http://127.0.0.1:5173,http://127.0.0.1:4173'
    network_hourly_sends: int = Field(default=20, ge=3, le=100)
    require_auth_for_analysis: bool = True
    llm_price_verified: bool = False
    auth_session_days: int = Field(default=30, ge=1, le=90)
    daily_free_analyses: int = Field(default=3, ge=1, le=20)
    recurring_daily_free_analyses: int = Field(default=1, ge=1, le=20)
    daily_quota_timezone: str = "Asia/Yekaterinburg"
    quota_reservation_seconds: int = Field(default=240, ge=90, le=900)
    max_image_bytes: int = Field(default=8_000_000, ge=100_000, le=20_000_000)
    max_image_pixels: int = Field(default=36_000_000, ge=1_000_000, le=80_000_000)
    min_image_edge: int = Field(default=32, ge=32, le=2_000)

    @property
    def polza_chat_url(self) -> str:
        return f"{self.polza_base_url.rstrip('/')}/chat/completions"


@lru_cache
def get_settings() -> Settings:
    return Settings()
