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
    frontend_public_base_url: str | None = Field(default=None, alias="FRONTEND_PUBLIC_BASE_URL")
    media_max_size_mb: int = Field(default=5, alias="MEDIA_MAX_SIZE_MB")
    smtp_host: str | None = Field(default=None, alias="SMTP_HOST")
    smtp_port: int = Field(default=587, alias="SMTP_PORT")
    smtp_username: str | None = Field(default=None, alias="SMTP_USERNAME")
    smtp_password: str | None = Field(default=None, alias="SMTP_PASSWORD")
    smtp_from_email: str | None = Field(default=None, alias="SMTP_FROM_EMAIL")
    smtp_from_name: str = Field(default="Nuvly", alias="SMTP_FROM_NAME")
    smtp_use_tls: bool = Field(default=True, alias="SMTP_USE_TLS")
    support_contact_email: str = Field(default="nuvlystudio@gmail.com", alias="SUPPORT_CONTACT_EMAIL")
    auth_session_ttl_days: int = Field(default=30, gt=0, alias="AUTH_SESSION_TTL_DAYS")
    auth_reset_password_ttl_minutes: int = Field(default=10, alias="AUTH_RESET_PASSWORD_TTL_MINUTES")

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
            "Invalid environment configuration. Check MONGODB_URI, MONGODB_DB_NAME, API_PREFIX, CORS_ORIGINS, PUBLIC_BASE_URL, FRONTEND_PUBLIC_BASE_URL, MEDIA_MAX_SIZE_MB, SMTP_*, SUPPORT_CONTACT_EMAIL, AUTH_SESSION_TTL_DAYS and AUTH_RESET_PASSWORD_TTL_MINUTES. "
            f"Details: {details}"
        ) from exc
