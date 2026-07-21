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

    # Email
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    email_from: str = ""

    # Embedding model - BGE is optimized for retrieval/search tasks
    embedding_model: str = "BAAI/bge-base-en-v1.5"
    embedding_dim: int = 768

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
