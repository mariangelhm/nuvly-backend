from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import logging
import secrets
from typing import Any, Literal

from app.core.config import get_settings
from app.core.errors import NuvlyError
from app.core.utils import new_id, utc_now_iso
from app.modules.auth.email_service import AuthEmailService
from app.modules.auth.repository import AuthRepository
from app.modules.auth.schemas import (
    ForgotPasswordRequest,
    LoginRequest,
    RegisterRequest,
    ResetPasswordRequest,
)

PASSWORD_HASH_ITERATIONS = 120_000
PASSWORD_SALT_BYTES = 16
AuthScope = Literal["customer", "internal"]
InternalRole = Literal["admin", "developer"]
logger = logging.getLogger(__name__)


class AuthService:
    def __init__(
        self,
        repository: AuthRepository | None = None,
        email_service: AuthEmailService | None = None,
        session_ttl_days: int | None = None,
    ) -> None:
        self.repository = repository or AuthRepository()
        self.email_service = email_service or AuthEmailService()
        self.session_ttl_days = session_ttl_days

    @staticmethod
    def _normalize_email(email: str) -> str:
        return email.strip().lower()

    @staticmethod
    def _utc_expires_at(days: int) -> str:
        return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()

    @staticmethod
    def _hash_password(password: str) -> str:
        salt = secrets.token_bytes(PASSWORD_SALT_BYTES)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PASSWORD_HASH_ITERATIONS)
        salt_b64 = base64.b64encode(salt).decode("ascii")
        digest_b64 = base64.b64encode(digest).decode("ascii")
        return f"pbkdf2_sha256${PASSWORD_HASH_ITERATIONS}${salt_b64}${digest_b64}"

    @staticmethod
    def _verify_password(password: str, stored_hash: str) -> bool:
        try:
            algorithm, iterations, salt_b64, digest_b64 = stored_hash.split("$", 3)
        except ValueError:
            return False
        if algorithm != "pbkdf2_sha256":
            return False
        salt = base64.b64decode(salt_b64.encode("ascii"))
        expected_digest = base64.b64decode(digest_b64.encode("ascii"))
        actual_digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, int(iterations))
        return hmac.compare_digest(actual_digest, expected_digest)

    @staticmethod
    def _hash_token(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    @staticmethod
    def _parse_iso_datetime(value: str | None) -> datetime | None:
        if not value:
            return None
        try:
            normalized = value.replace("Z", "+00:00")
            parsed = datetime.fromisoformat(normalized)
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except ValueError:
            return None

    @staticmethod
    def _to_user_response(document: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": document["id"],
            "name": document["name"],
            "email": document["email"],
            "accountType": document.get("accountType", "customer"),
            "internalRole": document.get("internalRole"),
            "emailVerified": document.get("emailVerified", False),
            "active": document.get("active", True),
            "authProviders": document.get("authProviders", []),
            "createdAt": document["createdAt"],
            "updatedAt": document["updatedAt"],
            "lastLoginAt": document.get("lastLoginAt"),
        }

    def _create_session_response(
        self,
        user: dict[str, Any],
        auth_provider: str = "nuvly",
        auth_scope: AuthScope = "customer",
    ) -> dict[str, Any]:
        now = utc_now_iso()
        settings = get_settings()
        session_ttl_days = self.session_ttl_days if self.session_ttl_days is not None else settings.auth_session_ttl_days
        expires_at = self._utc_expires_at(session_ttl_days)
        token = secrets.token_urlsafe(48)
        self.repository.insert_session(
            {
                "id": new_id("sess"),
                "userId": user["id"],
                "authProvider": auth_provider,
                "authScope": auth_scope,
                "tokenHash": self._hash_token(token),
                "active": True,
                "createdAt": now,
                "updatedAt": now,
                "expiresAt": expires_at,
                "revokedAt": None,
            }
        )
        return {
            "token": token,
            "tokenType": "bearer",
            "expiresAt": expires_at,
            "authProvider": auth_provider,
            "authScope": auth_scope,
            "user": self._to_user_response(user),
        }

    def _build_reset_password_url(self, raw_token: str) -> str:
        settings = get_settings()
        base_url = (settings.frontend_public_base_url or settings.public_base_url or "http://localhost:5173").rstrip("/")
        return f"{base_url}/reset-password?token={raw_token}"

    def ensure_internal_user(
        self,
        *,
        email: str,
        password: str,
        name: str = "Nuvly",
        internal_role: InternalRole = "admin",
    ) -> dict[str, Any]:
        normalized_email = self._normalize_email(email)
        now = utc_now_iso()
        existing = self.repository.find_user_by_email(normalized_email)
        password_hash = self._hash_password(password)
        provider_link = {
            "email": normalized_email,
            "passwordHash": password_hash,
            "linkedAt": now,
        }

        if existing:
            updated = dict(existing)
            updated["name"] = name
            updated["email"] = normalized_email
            updated["emailNormalized"] = normalized_email
            updated["accountType"] = "internal"
            updated["internalRole"] = internal_role
            updated["emailVerified"] = True
            updated["active"] = True
            auth_providers = list(updated.get("authProviders", []))
            if "nuvly" not in auth_providers:
                auth_providers.append("nuvly")
            updated["authProviders"] = auth_providers
            provider_links = dict(updated.get("providerLinks", {}))
            provider_links["nuvly"] = provider_link
            updated["providerLinks"] = provider_links
            updated["updatedAt"] = now
            self.repository.replace_user(updated["id"], updated)
            return updated

        document = {
            "id": new_id("usr"),
            "name": name,
            "email": normalized_email,
            "emailNormalized": normalized_email,
            "accountType": "internal",
            "internalRole": internal_role,
            "emailVerified": True,
            "active": True,
            "authProviders": ["nuvly"],
            "providerLinks": {"nuvly": provider_link},
            "createdAt": now,
            "updatedAt": now,
            "lastLoginAt": None,
        }
        return self.repository.insert_user(document)

    def create_internal_user(
        self,
        *,
        email: str,
        password: str,
        name: str,
        internal_role: InternalRole,
    ) -> dict[str, Any]:
        normalized_email = self._normalize_email(email)
        existing = self.repository.find_user_by_email(normalized_email)
        if existing:
            raise NuvlyError("Ya existe una cuenta registrada con ese email.", 409, "EMAIL_ALREADY_REGISTERED")
        return self.ensure_internal_user(
            email=normalized_email,
            password=password,
            name=name.strip(),
            internal_role=internal_role,
        )

    def register(self, payload: RegisterRequest) -> dict[str, Any]:
        normalized_email = self._normalize_email(str(payload.email))
        now = utc_now_iso()
        user = self.repository.insert_user(
            {
                "id": new_id("usr"),
                "name": payload.name.strip(),
                "email": normalized_email,
                "emailNormalized": normalized_email,
                "accountType": "customer",
                "emailVerified": False,
                "active": True,
                "authProviders": ["nuvly"],
                "providerLinks": {
                    "nuvly": {
                        "email": normalized_email,
                        "passwordHash": self._hash_password(payload.password),
                        "linkedAt": now,
                    }
                },
                "createdAt": now,
                "updatedAt": now,
                "lastLoginAt": now,
            }
        )
        return self._create_session_response(user, auth_scope="customer")

    def login(self, payload: LoginRequest) -> dict[str, Any]:
        return self._login_with_account_type(payload, "customer")

    def login_internal(self, payload: LoginRequest) -> dict[str, Any]:
        return self._login_with_account_type(payload, "internal")

    def _login_with_account_type(self, payload: LoginRequest, expected_account_type: AuthScope) -> dict[str, Any]:
        normalized_email = self._normalize_email(str(payload.email))
        user = self.repository.find_user_by_email(normalized_email)
        if not user:
            raise NuvlyError("Email o contraseña incorrectos.", 401, "INVALID_CREDENTIALS")
        if not user.get("active", True):
            raise NuvlyError("La cuenta está desactivada.", 403, "USER_INACTIVE")
        if user.get("accountType", "customer") != expected_account_type:
            raise NuvlyError("Email o contraseña incorrectos.", 401, "INVALID_CREDENTIALS")

        provider_data = ((user.get("providerLinks") or {}).get("nuvly") or {})
        stored_hash = provider_data.get("passwordHash")
        if not stored_hash or not self._verify_password(payload.password, stored_hash):
            raise NuvlyError("Email o contraseña incorrectos.", 401, "INVALID_CREDENTIALS")

        updated_user = dict(user)
        updated_user["lastLoginAt"] = utc_now_iso()
        updated_user["updatedAt"] = updated_user["lastLoginAt"]
        user = self.repository.replace_user(user["id"], updated_user)
        return self._create_session_response(user, auth_scope=expected_account_type)

    def get_user_from_token(self, token: str, required_account_type: AuthScope | None = None) -> dict[str, Any]:
        session = self.repository.find_session_by_token_hash(self._hash_token(token))
        if not session or not session.get("active", False):
            raise NuvlyError("Sesion invalida o expirada.", 401, "INVALID_SESSION")

        expires_at = self._parse_iso_datetime(session.get("expiresAt"))
        if expires_at is None or expires_at <= datetime.now(timezone.utc):
            raise NuvlyError("Sesion invalida o expirada.", 401, "INVALID_SESSION")

        user = self.repository.find_user_by_id(session["userId"])
        if not user:
            raise NuvlyError("Usuario de la sesion no encontrado.", 401, "SESSION_USER_NOT_FOUND")
        if not user.get("active", True):
            raise NuvlyError("La cuenta está desactivada.", 403, "USER_INACTIVE")
        if required_account_type and user.get("accountType", "customer") != required_account_type:
            raise NuvlyError("No tienes permisos para acceder a este recurso.", 403, "AUTH_SCOPE_FORBIDDEN")
        return self._to_user_response(user)

    def logout(self, token: str) -> dict[str, Any]:
        session = self.repository.find_session_by_token_hash(self._hash_token(token))
        if not session:
            return {"ok": True}
        session["active"] = False
        session["revokedAt"] = utc_now_iso()
        session["updatedAt"] = session["revokedAt"]
        self.repository.replace_session(session["id"], session)
        return {"ok": True}

    def forgot_password(self, payload: ForgotPasswordRequest) -> dict[str, Any]:
        normalized_email = self._normalize_email(payload.email)
        logger.info("Forgot password requested | email=%s", normalized_email)
        user = self.repository.find_user_by_email(normalized_email)
        generic_response = {"ok": True, "message": "Si el email existe, enviaremos un enlace para recuperar la clave."}
        if not user:
            logger.info("Forgot password skipped | email=%s reason=user_not_found", normalized_email)
            return generic_response
        if not user.get("active", True):
            logger.info("Forgot password skipped | email=%s userId=%s reason=user_inactive", normalized_email, user["id"])
            return generic_response

        now = utc_now_iso()
        settings = get_settings()
        raw_token = secrets.token_urlsafe(48)
        expires_at = self._utc_expires_at(days=0)
        expires_dt = datetime.now(timezone.utc) + timedelta(minutes=settings.auth_reset_password_ttl_minutes)
        expires_at = expires_dt.isoformat()
        self.repository.insert_password_reset_token(
            {
                "id": new_id("rst"),
                "userId": user["id"],
                "email": user["email"],
                "tokenHash": self._hash_token(raw_token),
                "createdAt": now,
                "updatedAt": now,
                "expiresAt": expires_at,
                "usedAt": None,
            }
        )
        logger.info("Password reset token stored | userId=%s email=%s expiresAt=%s", user["id"], user["email"], expires_at)
        reset_url = self._build_reset_password_url(raw_token)
        logger.info("Password reset token generated | userId=%s email=%s expiresAt=%s", user["id"], user["email"], expires_at)
        logger.info("Password reset email dispatch started | userId=%s email=%s", user["id"], user["email"])
        self.email_service.send_password_reset_email(user["email"], reset_url)
        logger.info("Password reset flow completed | userId=%s email=%s", user["id"], user["email"])
        return generic_response

    def reset_password(self, payload: ResetPasswordRequest) -> dict[str, Any]:
        token_document = self.repository.find_password_reset_token_by_hash(self._hash_token(payload.token))
        if not token_document:
            raise NuvlyError("Token de recuperacion invalido o expirado.", 400, "INVALID_RESET_TOKEN")
        if token_document.get("usedAt"):
            raise NuvlyError("Token de recuperacion invalido o expirado.", 400, "INVALID_RESET_TOKEN")
        expires_at = self._parse_iso_datetime(token_document.get("expiresAt"))
        if expires_at is None or expires_at <= datetime.now(timezone.utc):
            raise NuvlyError("Token de recuperacion invalido o expirado.", 400, "INVALID_RESET_TOKEN")

        user = self.repository.find_user_by_id(token_document["userId"])
        if not user:
            raise NuvlyError("Usuario no encontrado para el token de recuperacion.", 404, "USER_NOT_FOUND")

        now = utc_now_iso()
        updated_user = dict(user)
        provider_links = dict(updated_user.get("providerLinks") or {})
        nuvly_provider = dict(provider_links.get("nuvly") or {})
        nuvly_provider["email"] = updated_user["email"]
        nuvly_provider["passwordHash"] = self._hash_password(payload.password)
        nuvly_provider["linkedAt"] = nuvly_provider.get("linkedAt") or now
        provider_links["nuvly"] = nuvly_provider
        updated_user["providerLinks"] = provider_links
        updated_user["authProviders"] = sorted(set((updated_user.get("authProviders") or []) + ["nuvly"]))
        updated_user["updatedAt"] = now
        self.repository.replace_user(updated_user["id"], updated_user)

        token_document["usedAt"] = now
        token_document["updatedAt"] = now
        self.repository.replace_password_reset_token(token_document["id"], token_document)
        return {"ok": True}
