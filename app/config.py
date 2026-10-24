from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg2://leadflow:leadflow@localhost:5432/leadflow"
    redis_url: str = "redis://localhost:6379/0"
    redis_enabled: bool = True
    secret_key: str = "change-me"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    cache_ttl_seconds: int = 60
    rate_limit_per_minute: int = 100


settings = Settings()
