from functools import lru_cache
from os import getenv

from pydantic_settings import BaseSettings, SettingsConfigDict

# Default to local PostgreSQL if no DB config is provided
DEFAULT_DB_URL = "postgresql://postgres:postgres@localhost:5432/postgres"
DEFAULT_ASYNC_DB_URL = "postgresql+asyncpg://postgres:postgres@localhost:5432/postgres"

# Get DB config from environment
DB_USER = getenv("DB_USER", "postgres")
DB_PASSWORD = getenv("DB_PASSWORD", "postgres")
DB_HOST = getenv("DB_HOST", "localhost")
DB_PORT = getenv("DB_PORT", "5432")
DB_NAME = getenv("DB_NAME", "postgres")

# Build PostgreSQL URL
POSTGRES_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
POSTGRES_ASYNC_URL = (
    f"postgresql+asyncpg://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(arbitrary_types_allowed=True)

    # Database settings
    DATABASE_URL: str = getenv("DATABASE_URL", POSTGRES_URL)
    ASYNC_DATABASE_URL: str = getenv("ASYNC_DATABASE_URL", POSTGRES_ASYNC_URL)
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 10
    DB_ECHO_LOG: bool = False

    # API settings
    API_V1_STR: str = "/api"

    # Security settings
    JWT_SECRET_KEY: str = getenv("JWT_SECRET_KEY", "test_secret_key")
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    JWT_REFRESH_TOKEN_EXPIRE_MINUTES: int = 30 * 60 * 24

    # CORS settings
    CORS_ORIGINS: list[str] = (
        getenv("CORS_ORIGINS", "").split(",") if getenv("CORS_ORIGINS") else []
    )

    # AWS settings
    AWS_ACCESS_KEY_ID: str = getenv("AWS_ACCESS_KEY_ID", "")
    AWS_SECRET_ACCESS_KEY: str = getenv("AWS_SECRET_ACCESS_KEY", "")
    AWS_REGION_NAME: str = getenv("AWS_REGION_NAME", "")
    AWS_S3_BUCKET_NAME: str = getenv("AWS_S3_BUCKET_NAME", "")

    # Langchain settings
    LANGCHAIN_API_KEY: str = getenv("LANGCHAIN_API_KEY", "")
    LANGCHAIN_TRACING_V2: bool = True
    LANGCHAIN_ENDPOINT: str = getenv("LANGCHAIN_ENDPOINT", "")
    LANGCHAIN_PROJECT: str = getenv("LANGCHAIN_PROJECT", "")

    # OpenAI settings
    OPENAI_API_KEY: str = getenv("OPENAI_API_KEY", "")
    OPENAI_ASSISTANT_MODEL: str = getenv("OPENAI_ASSISTANT_MODEL", "gpt-4")
    OPENAI_EMBEDDING_MODEL: str = getenv(
        "OPENAI_EMBEDDING_MODEL", "text-embedding-3-large"
    )


@lru_cache
def get_settings() -> Settings:
    """
    Cache and return settings instance
    """
    return Settings()
