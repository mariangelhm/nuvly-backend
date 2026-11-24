from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from app.core.config import get_settings
from app.core.errors import NuvlyError
from app.core.utils import new_id, utc_now_iso
from app.modules.auth.email_service import AuthEmailService
from app.modules.auth.google_identity import verify_google_credential
from app.modules.auth.repository import AuthRepository
from app.modules.auth.schemas import (
    ForgotPasswordRequest,
    GoogleLoginRequest,
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
        if not isinstance(stored_hash, str):
            return False
        try:
            algorithm, iterations_text, salt_b64, digest_b64 = stored_hash.split("$", 3)
            iterations = int(iterations_text)
            if algorithm != "pbkdf2_sha256" or not 1 <= iterations <= 2_000_000:
                return False
            salt = base64.b64decode(salt_b64, validate=True)
            expected_digest = base64.b64decode(digest_b64, validate=True)
            if len(salt) != PASSWORD_SALT_BYTES or len(expected_digest) != 32:
                return False
            actual_digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
        except ValueError, TypeError, binascii.Error:
            return False
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
        session_ttl_days = (
            self.session_ttl_days if self.session_ttl_days is not None else settings.auth_session_ttl_days
        )
        expires_at = self._utc_expires_at(session_ttl_days)
        token = secrets.token_urlsafe(48)
        self.repository.insert_session(
            {
                "id": new_id("sess"),
                "userId": user["id"],
                "authProvider": auth_provider,
                "authScope": auth_scope,
                "tokenHash": self._hash_token(token),
                "credentialsVersion": user.get("credentialsVersion"),
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
        base_url = (settings.frontend_public_base_url or settings.public_base_url or "http://localhost:5173").rstrip(
            "/"
        )
        return f"{base_url}/reset-password?token={raw_token}"

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
        now = utc_now_iso()
        password_hash = self._hash_password(password)
        provider_link = {
            "email": normalized_email,
            "passwordHash": password_hash,
            "linkedAt": now,
        }

        document = {
            "id": new_id("usr"),
            "name": name.strip(),
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

    def create_google_challenge(self) -> dict[str, str]:
        client_id = (get_settings().google_client_id or "").strip()
        if not client_id:
            raise NuvlyError("El acceso con Google todavía no está disponible.", 503, "GOOGLE_AUTH_NOT_CONFIGURED")
        token = secrets.token_urlsafe(32)
        nonce = secrets.token_urlsafe(32)
        now = datetime.now(timezone.utc)
        self.repository.insert_google_challenge(
            {
                "tokenHash": self._hash_token(token),
                "nonce": nonce,
                "createdAt": now,
                "expiresAt": now + timedelta(minutes=10),
            }
        )
        return {"clientId": client_id, "nonce": nonce, "challengeToken": token}

    def login_google(self, payload: GoogleLoginRequest) -> dict[str, Any]:
        client_id = (get_settings().google_client_id or "").strip()
        if not client_id:
            raise NuvlyError("El acceso con Google todavía no está disponible.", 503, "GOOGLE_AUTH_NOT_CONFIGURED")
        challenge = self.repository.consume_google_challenge(
            self._hash_token(payload.challengeToken),
            datetime.now(timezone.utc),
        )
        if not challenge:
            raise NuvlyError("El acceso con Google expiró. Inténtalo nuevamente.", 401, "GOOGLE_CHALLENGE_EXPIRED")
        claims = verify_google_credential(payload.credential, client_id)
        subject = claims.get("sub")
        email = claims.get("email")
        nonce = claims.get("nonce")
        if (
            not isinstance(subject, str)
            or not subject.strip()
            or not isinstance(email, str)
            or "@" not in email
            or claims.get("email_verified") is not True
            or not isinstance(nonce, str)
            or not hmac.compare_digest(nonce, challenge["nonce"])
        ):
            raise NuvlyError(
                "No pudimos verificar tu acceso con Google. Inténtalo nuevamente.", 401, "INVALID_GOOGLE_CREDENTIAL"
            )

        normalized_email = self._normalize_email(email)
        user = self.repository.find_user_by_google_subject(subject)
        if not user:
            user = self.repository.find_user_by_email(normalized_email)
            if user:
                existing_subject = ((user.get("providerLinks") or {}).get("google") or {}).get("subject")
                # Google is authoritative for Gmail and verified Workspace emails.
                # Other existing accounts require explicit, authenticated linking.
                authoritative_email = normalized_email.endswith("@gmail.com") or bool(claims.get("hd"))
                if existing_subject and existing_subject != subject:
                    raise NuvlyError(
                        "Esta cuenta ya está vinculada a otra identidad de Google.", 409, "GOOGLE_ACCOUNT_CONFLICT"
                    )
                if not existing_subject and not authoritative_email:
                    raise NuvlyError(
                        "Ya tienes una cuenta con este correo. Ingresa con tu contraseña.",
                        409,
                        "GOOGLE_ACCOUNT_LINK_REQUIRED",
                    )
        now = utc_now_iso()
        if user:
            if user.get("accountType", "customer") != "customer":
                raise NuvlyError("Usa el acceso del equipo para esta cuenta.", 403, "GOOGLE_CUSTOMER_ONLY")
            if not user.get("active", True):
                raise NuvlyError("La cuenta está desactivada.", 403, "USER_INACTIVE")
            updated = dict(user)
            providers = list(user.get("authProviders") or [])
            if "google" not in providers:
                providers.append("google")
            updated.update(
                {
                    "authProviders": providers,
                    "providerLinks": {
                        **(user.get("providerLinks") or {}),
                        "google": {
                            "subject": subject,
                            "email": normalized_email,
                            "linkedAt": ((user.get("providerLinks") or {}).get("google") or {}).get("linkedAt", now),
                        },
                    },
                    "emailVerified": True,
                    "lastLoginAt": now,
                    "updatedAt": now,
                }
            )
            user = self.repository.link_google_identity(user["id"], updated["providerLinks"]["google"], now)
        else:
            user = self.repository.insert_user(
                {
                    "id": new_id("usr"),
                    "name": (str(claims.get("name") or "").strip() or normalized_email.split("@", 1)[0])[:120],
                    "email": normalized_email,
                    "emailNormalized": normalized_email,
                    "accountType": "customer",
                    "emailVerified": True,
                    "active": True,
                    "authProviders": ["google"],
                    "providerLinks": {"google": {"subject": subject, "email": normalized_email, "linkedAt": now}},
                    "createdAt": now,
                    "updatedAt": now,
                    "lastLoginAt": now,
                }
            )
        return self._create_session_response(user, auth_provider="google", auth_scope="customer")

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

        provider_data = (user.get("providerLinks") or {}).get("nuvly") or {}
        stored_hash = provider_data.get("passwordHash")
        if not stored_hash or not self._verify_password(payload.password, stored_hash):
            raise NuvlyError("Email o contraseña incorrectos.", 401, "INVALID_CREDENTIALS")

        user = self.repository.record_password_login(user["id"], user.get("credentialsVersion"), utc_now_iso())
        if user is None:
            raise NuvlyError("Email o contraseña incorrectos.", 401, "INVALID_CREDENTIALS")
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
        if session.get("credentialsVersion") != user.get("credentialsVersion"):
            raise NuvlyError("Sesion invalida o expirada.", 401, "INVALID_SESSION")
        if session.get("authScope", "customer") != user.get("accountType", "customer"):
            raise NuvlyError("No tienes permisos para acceder a este recurso.", 403, "AUTH_SCOPE_FORBIDDEN")
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
            logger.info(
                "Forgot password skipped | email=%s userId=%s reason=user_inactive", normalized_email, user["id"]
            )
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
                "credentialsVersion": user.get("credentialsVersion"),
                "createdAt": now,
                "updatedAt": now,
                "expiresAt": expires_at,
                "usedAt": None,
            }
        )
        logger.info(
            "Password reset token stored | userId=%s email=%s expiresAt=%s", user["id"], user["email"], expires_at
        )
        reset_url = self._build_reset_password_url(raw_token)
        logger.info(
            "Password reset token generated | userId=%s email=%s expiresAt=%s", user["id"], user["email"], expires_at
        )
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

        if token_document.get("credentialsVersion") != user.get("credentialsVersion"):
            raise NuvlyError("Token de recuperacion invalido o expirado.", 400, "INVALID_RESET_TOKEN")
        now = utc_now_iso()
        updated_user = dict(user)
        provider_links = dict(updated_user.get("providerLinks") or {})
        nuvly_provider = dict(provider_links.get("nuvly") or {})
        nuvly_provider["email"] = updated_user["email"]
        nuvly_provider["passwordHash"] = self._hash_password(payload.password)
        nuvly_provider["linkedAt"] = nuvly_provider.get("linkedAt") or now
        provider_links["nuvly"] = nuvly_provider
        updated_user["providerLinks"] = provider_links
        updated_user["credentialsVersion"] = secrets.token_urlsafe(24)
        updated_user["authProviders"] = sorted(set((updated_user.get("authProviders") or []) + ["nuvly"]))
        updated_user["updatedAt"] = now
        # Claim before mutating the password: simultaneous reuse must have one winner.
        if not self.repository.consume_password_reset_token(token_document["id"], now):
            raise NuvlyError("Token de recuperacion invalido o expirado.", 400, "INVALID_RESET_TOKEN")
        if not self.repository.update_password_credentials(
            user["id"],
            user.get("credentialsVersion"),
            nuvly_provider,
            updated_user["authProviders"],
            updated_user["credentialsVersion"],
            now,
        ):
            raise NuvlyError("Token de recuperacion invalido o expirado.", 400, "INVALID_RESET_TOKEN")
        return {"ok": True}
