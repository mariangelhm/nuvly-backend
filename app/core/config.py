from functools import lru_cache
from typing import List

from pydantic import Field
from pydantic import ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = Field(default="Nuvly Backend", alias="APP_NAME")
    app_env: str = Field(default="development", alias="APP_ENV")
    api_prefix: str = Field(default="/api", alias="API_PREFIX")
    mongodb_uri: str = Field(alias="MONGODB_URI")
    mongodb_db_name: str = Field(default="nuvly_dev", alias="MONGODB_DB_NAME")
    cors_origins: str = Field(
        default="http://localhost:5173,http://localhost:3000",
        alias="CORS_ORIGINS",
    )
    public_base_url: str | None = Field(default=None, alias="PUBLIC_BASE_URL")
    media_max_size_mb: int = Field(default=5, alias="MEDIA_MAX_SIZE_MB")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    @property
    def cors_origin_list(self) -> List[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def media_max_size_bytes(self) -> int:
        return self.media_max_size_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    try:
        return Settings()
    except ValidationError as exc:
        missing_or_invalid = []
        for error in exc.errors():
            field_name = ".".join(str(part) for part in error.get("loc", ()))
            if field_name:
                missing_or_invalid.append(field_name)
        details = ", ".join(missing_or_invalid) if missing_or_invalid else str(exc)
        raise RuntimeError(
            "Invalid environment configuration. Check MONGODB_URI, MONGODB_DB_NAME, API_PREFIX, CORS_ORIGINS, PUBLIC_BASE_URL and MEDIA_MAX_SIZE_MB. "
            f"Details: {details}"
        ) from exc
