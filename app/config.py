from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql://postgres:dev@localhost:5432/jobmatch"

    # Adzuna
    adzuna_app_id: str = ""
    adzuna_app_key: str = ""

    # Reed.co.uk
    reed_api_key: str = ""

    # OpenAI
    openai_api_key: str = ""
    openai_model: str = "gpt-5.6-sol"

    # JWT Auth
    secret_key: str = "change-this-to-a-random-string"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 1440
    app_base_url: str = "http://localhost:5000"
    password_reset_expiry_minutes: int = 15

    # Email
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    email_from: str = ""
    smtp_timeout_seconds: int = 10

    # Dedicated notification scheduler process
    scheduler_enabled: bool = False
    scheduler_timezone: str = "UTC"
    scheduler_instant_interval_minutes: int = 15
    scheduler_daily_time: str = "09:00"
    scheduler_weekly_day: str = "mon"
    scheduler_weekly_time: str = "09:00"
    notification_max_retries: int = 3
    notification_digest_limit: int = 5
    recommended_search_threshold: float = 0.35

    # Embedding model - BGE is optimized for retrieval/search tasks
    embedding_model: str = "BAAI/bge-base-en-v1.5"
    embedding_dim: int = 768

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
