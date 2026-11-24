from functools import lru_cache
from typing import List
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, ValidationError, field_validator, model_validator
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
    payments_environment: str = Field(default="integration", alias="PAYMENTS_ENVIRONMENT")
    payments_production_enabled: bool = Field(default=False, alias="PAYMENTS_PRODUCTION_ENABLED")
    transbank_commerce_code: str | None = Field(default=None, alias="TRANSBANK_COMMERCE_CODE")
    transbank_api_key: SecretStr | None = Field(default=None, alias="TRANSBANK_API_KEY")
    mercadopago_test_access_token: SecretStr | None = Field(default=None, alias="MERCADOPAGO_TEST_ACCESS_TOKEN")
    mercadopago_test_webhook_secret: SecretStr | None = Field(default=None, alias="MERCADOPAGO_TEST_WEBHOOK_SECRET")
    media_max_size_mb: int = Field(default=5, gt=0, alias="MEDIA_MAX_SIZE_MB")
    media_owner_daily_upload_mb: int = Field(default=100, gt=0, alias="MEDIA_OWNER_DAILY_UPLOAD_MB")
    media_storage_root: str | None = Field(default=None, alias="MEDIA_STORAGE_ROOT")
    media_storage_durable: bool = Field(default=False, alias="MEDIA_STORAGE_DURABLE")
    smtp_host: str | None = Field(default=None, alias="SMTP_HOST")
    smtp_port: int = Field(default=587, alias="SMTP_PORT")
    smtp_username: str | None = Field(default=None, alias="SMTP_USERNAME")
    smtp_password: str | None = Field(default=None, alias="SMTP_PASSWORD")
    smtp_from_email: str | None = Field(default=None, alias="SMTP_FROM_EMAIL")
    smtp_from_name: str = Field(default="Nuvly", alias="SMTP_FROM_NAME")
    smtp_use_tls: bool = Field(default=True, alias="SMTP_USE_TLS")
    support_contact_email: str = Field(default="nuvlystudio@gmail.com", alias="SUPPORT_CONTACT_EMAIL")
    auth_session_ttl_days: int = Field(default=30, gt=0, alias="AUTH_SESSION_TTL_DAYS")
    google_client_id: str | None = Field(default=None, alias="GOOGLE_CLIENT_ID")
    auth_reset_password_ttl_minutes: int = Field(default=10, gt=0, alias="AUTH_RESET_PASSWORD_TTL_MINUTES")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    @field_validator("app_env")
    @classmethod
    def normalize_app_env(cls, value: str) -> str:
        return value.strip().lower()

    @field_validator("cors_origins")
    @classmethod
    def validate_cors_origins(cls, value: str) -> str:
        origins = [origin.strip() for origin in value.split(",") if origin.strip()]
        for origin in origins:
            parsed = urlsplit(origin)
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.hostname
                or parsed.username
                or parsed.password
                or parsed.path
                or parsed.query
                or parsed.fragment
                or "*" in origin
            ):
                raise ValueError("CORS_ORIGINS requires explicit HTTP(S) origins without paths or wildcards")
        if not origins:
            raise ValueError("At least one trusted frontend origin is required")
        return ",".join(origins)

    @model_validator(mode="after")
    def validate_production_origins(self):
        if self.app_env in {"production", "prod"}:
            for value in (self.public_base_url, self.frontend_public_base_url):
                parsed = urlsplit(value or "")
                if (
                    parsed.scheme != "https"
                    or not parsed.hostname
                    or parsed.username
                    or parsed.password
                    or parsed.path not in {"", "/"}
                    or parsed.query
                    or parsed.fragment
                ):
                    raise ValueError("Production requires explicit HTTPS backend and frontend origins")
            if any(not origin.startswith("https://") for origin in self.cors_origin_list):
                raise ValueError("Production CORS origins must use HTTPS")
            if self.frontend_public_base_url.rstrip("/") not in self.cors_origin_list:
                raise ValueError("The production frontend must be an explicitly trusted CORS origin")
        return self

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
