from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    SUPABASE_URL: str
    SUPABASE_SERVICE_ROLE_KEY: str
    SUPABASE_JWT_SECRET: str
    GEMINI_API_KEY: str
    LINKD_API_KEY: str
    UPSTASH_REDIS_URL: str
    UPSTASH_REDIS_TOKEN: str
    RESEND_API_KEY: str = ""
    ENVIRONMENT: str = "qa"
    LOG_LEVEL: str = "DEBUG"

    model_config = SettingsConfigDict(
        env_file=".env.qa",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )

    @property
    def is_prod(self) -> bool:
        return self.ENVIRONMENT == "prod"


@lru_cache
def get_settings() -> Settings:
    return Settings()
