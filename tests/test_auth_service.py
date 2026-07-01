from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

import app.main as main_module
from app.core.config import get_settings
from app.core.errors import NuvlyError
from app.modules.auth import dependencies as auth_dependencies
from app.modules.auth.email_service import AuthEmailService
from app.modules.auth.schemas import ForgotPasswordRequest, LoginRequest, RegisterRequest, ResetPasswordRequest
from app.modules.auth.service import AuthService


class InMemoryAuthRepository:
    def __init__(self) -> None:
        self.users: list[dict[str, Any]] = []
        self.sessions: list[dict[str, Any]] = []
        self.reset_tokens: list[dict[str, Any]] = []

    def find_user_by_email(self, email_normalized: str) -> dict[str, Any] | None:
        for user in self.users:
            if user.get("emailNormalized") == email_normalized:
                return deepcopy(user)
        return None

    def find_user_by_id(self, user_id: str) -> dict[str, Any] | None:
        for user in self.users:
            if user.get("id") == user_id:
                return deepcopy(user)
        return None

    def insert_user(self, document: dict[str, Any]) -> dict[str, Any]:
        if any(user.get("emailNormalized") == document.get("emailNormalized") for user in self.users):
            raise NuvlyError("Ya existe una cuenta registrada con ese email.", 409, "EMAIL_ALREADY_REGISTERED")
        self.users.append(deepcopy(document))
        return deepcopy(document)

    def replace_user(self, user_id: str, document: dict[str, Any]) -> dict[str, Any]:
        for index, user in enumerate(self.users):
            if user.get("id") == user_id:
                self.users[index] = deepcopy(document)
                return deepcopy(document)
        raise AssertionError(f"User not found in test repository: {user_id}")

    def insert_session(self, document: dict[str, Any]) -> dict[str, Any]:
        self.sessions.append(deepcopy(document))
        return deepcopy(document)

    def find_session_by_token_hash(self, token_hash: str) -> dict[str, Any] | None:
        for session in self.sessions:
            if session.get("tokenHash") == token_hash:
                return deepcopy(session)
        return None

    def replace_session(self, session_id: str, document: dict[str, Any]) -> dict[str, Any]:
        for index, session in enumerate(self.sessions):
            if session.get("id") == session_id:
                self.sessions[index] = deepcopy(document)
                return deepcopy(document)
        raise AssertionError(f"Session not found in test repository: {session_id}")

    def insert_password_reset_token(self, document: dict[str, Any]) -> dict[str, Any]:
        self.reset_tokens.append(deepcopy(document))
        return deepcopy(document)

    def find_password_reset_token_by_hash(self, token_hash: str) -> dict[str, Any] | None:
        for token in self.reset_tokens:
            if token.get("tokenHash") == token_hash:
                return deepcopy(token)
        return None

    def replace_password_reset_token(self, token_id: str, document: dict[str, Any]) -> dict[str, Any]:
        for index, token in enumerate(self.reset_tokens):
            if token.get("id") == token_id:
                self.reset_tokens[index] = deepcopy(document)
                return deepcopy(document)
        raise AssertionError(f"Reset token not found in test repository: {token_id}")


class StubAuthEmailService:
    def __init__(self) -> None:
        self.sent_messages: list[dict[str, str]] = []

    def send_password_reset_email(self, email: str, reset_url: str) -> None:
        self.sent_messages.append({"email": email, "reset_url": reset_url})


class FailingAuthEmailService:
    def send_password_reset_email(self, email: str, reset_url: str) -> None:
        raise NuvlyError(
            "No pudimos enviar el correo de recuperacion. Revisa la configuracion SMTP e intentalo nuevamente.",
            502,
            "AUTH_EMAIL_SEND_FAILED",
        )


def test_register_creates_user_and_session() -> None:
    repository = InMemoryAuthRepository()
    service = AuthService(repository=repository)

    response = service.register(
        RegisterRequest(
            email="Lara@Test.dev",
            confirmEmail="lara@test.dev",
            password="Supersecret1#",
            confirmPassword="Supersecret1#",
            name="Lara",
        )
    )

    assert response["token"]
    assert response["authProvider"] == "nuvly"
    assert response["user"]["email"] == "lara@test.dev"
    assert response["user"]["name"] == "Lara"
    assert response["user"]["authProviders"] == ["nuvly"]
    assert len(repository.users) == 1
    assert len(repository.sessions) == 1
    assert repository.users[0]["providerLinks"]["nuvly"]["passwordHash"] != "supersecret123"
    assert response["authScope"] == "customer"
    assert response["user"]["accountType"] == "customer"


def test_session_expires_using_configured_ttl() -> None:
    settings = get_settings()
    previous_ttl = settings.auth_session_ttl_days
    settings.auth_session_ttl_days = 7
    try:
        repository = InMemoryAuthRepository()
        service = AuthService(repository=repository)

        response = service.register(
            RegisterRequest(
                email="Lara@Test.dev",
                confirmEmail="lara@test.dev",
                password="Supersecret1#",
                confirmPassword="Supersecret1#",
                name="Lara",
            )
        )

        expires_at = datetime.fromisoformat(response["expiresAt"].replace("Z", "+00:00"))
        delta = expires_at - datetime.now(timezone.utc)
        assert timedelta(days=6, hours=23) <= delta <= timedelta(days=7, minutes=1)
    finally:
        settings.auth_session_ttl_days = previous_ttl


def test_register_rejects_duplicate_email() -> None:
    repository = InMemoryAuthRepository()
    service = AuthService(repository=repository)
    payload = RegisterRequest(
        email="lara@test.dev",
        confirmEmail="lara@test.dev",
        password="Supersecret1#",
        confirmPassword="Supersecret1#",
        name="Lara",
    )

    service.register(payload)

    with pytest.raises(NuvlyError) as exc:
        service.register(payload)

    assert exc.value.status_code == 409
    assert exc.value.code == "EMAIL_ALREADY_REGISTERED"


def test_login_returns_new_session_for_valid_credentials() -> None:
    repository = InMemoryAuthRepository()
    service = AuthService(repository=repository)
    service.register(
        RegisterRequest(
            email="lara@test.dev",
            confirmEmail="lara@test.dev",
            password="Supersecret1#",
            confirmPassword="Supersecret1#",
            name="Lara",
        )
    )

    response = service.login(LoginRequest(email="LARA@test.dev", password="Supersecret1#"))

    assert response["token"]
    assert response["user"]["email"] == "lara@test.dev"
    assert response["authScope"] == "customer"
    assert len(repository.sessions) == 2


def test_login_rejects_invalid_password() -> None:
    repository = InMemoryAuthRepository()
    service = AuthService(repository=repository)
    service.register(
        RegisterRequest(
            email="lara@test.dev",
            confirmEmail="lara@test.dev",
            password="Supersecret1#",
            confirmPassword="Supersecret1#",
            name="Lara",
        )
    )

    with pytest.raises(NuvlyError) as exc:
        service.login(LoginRequest(email="lara@test.dev", password="Wrongpass1#"))

    assert exc.value.status_code == 401
    assert exc.value.code == "INVALID_CREDENTIALS"


def test_me_can_resolve_current_user_from_token() -> None:
    repository = InMemoryAuthRepository()
    service = AuthService(repository=repository)
    session = service.register(
        RegisterRequest(
            email="lara@test.dev",
            confirmEmail="lara@test.dev",
            password="Supersecret1#",
            confirmPassword="Supersecret1#",
            name="Lara",
        )
    )

    current_user = service.get_user_from_token(session["token"])

    assert current_user["email"] == "lara@test.dev"
    assert current_user["name"] == "Lara"
    assert current_user["accountType"] == "customer"


def test_internal_login_requires_internal_account_type() -> None:
    repository = InMemoryAuthRepository()
    repository.users.append(
        {
            "id": "usr_admin",
            "name": "Admin",
            "email": "admin@nuvly.dev",
            "emailNormalized": "admin@nuvly.dev",
            "accountType": "internal",
            "internalRole": "admin",
            "emailVerified": True,
            "active": True,
            "authProviders": ["nuvly"],
            "providerLinks": {
                "nuvly": {
                    "email": "admin@nuvly.dev",
                    "passwordHash": AuthService._hash_password("Adminpass1#"),
                    "linkedAt": "2026-06-30T00:00:00+00:00",
                }
            },
            "createdAt": "2026-06-30T00:00:00+00:00",
            "updatedAt": "2026-06-30T00:00:00+00:00",
            "lastLoginAt": None,
        }
    )
    service = AuthService(repository=repository)

    response = service.login_internal(LoginRequest(email="admin@nuvly.dev", password="Adminpass1#"))

    assert response["authScope"] == "internal"
    assert response["user"]["accountType"] == "internal"
    assert response["user"]["internalRole"] == "admin"

    with pytest.raises(NuvlyError) as exc:
        service.login(LoginRequest(email="admin@nuvly.dev", password="Adminpass1#"))
    assert exc.value.code == "INVALID_CREDENTIALS"


def test_logout_revokes_session_token() -> None:
    repository = InMemoryAuthRepository()
    service = AuthService(repository=repository)
    session = service.register(
        RegisterRequest(
            email="lara@test.dev",
            confirmEmail="lara@test.dev",
            password="Supersecret1#",
            confirmPassword="Supersecret1#",
            name="Lara",
        )
    )

    response = service.logout(session["token"])

    assert response["ok"] is True
    with pytest.raises(NuvlyError) as exc:
        service.get_user_from_token(session["token"])
    assert exc.value.code == "INVALID_SESSION"


def test_register_rejects_password_that_does_not_match_policy() -> None:
    with pytest.raises(ValueError):
        RegisterRequest(
            email="lara@test.dev",
            confirmEmail="lara@test.dev",
            password="supersecret123",
            confirmPassword="supersecret123",
            name="Lara",
        )


def test_forgot_password_returns_ok_even_if_email_does_not_exist() -> None:
    repository = InMemoryAuthRepository()
    email_service = StubAuthEmailService()
    service = AuthService(repository=repository, email_service=email_service)

    response = service.forgot_password(ForgotPasswordRequest(email="ghost@test.dev"))

    assert response["ok"] is True
    assert email_service.sent_messages == []
    assert repository.reset_tokens == []


def test_forgot_password_generates_token_and_sends_email() -> None:
    repository = InMemoryAuthRepository()
    email_service = StubAuthEmailService()
    service = AuthService(repository=repository, email_service=email_service)
    service.register(
        RegisterRequest(
            email="lara@test.dev",
            confirmEmail="lara@test.dev",
            password="Supersecret1#",
            confirmPassword="Supersecret1#",
            name="Lara",
        )
    )

    response = service.forgot_password(ForgotPasswordRequest(email="lara@test.dev"))

    assert response["ok"] is True
    assert len(repository.reset_tokens) == 1
    assert len(email_service.sent_messages) == 1
    assert email_service.sent_messages[0]["email"] == "lara@test.dev"
    assert "reset-password?token=" in email_service.sent_messages[0]["reset_url"]


def test_password_reset_email_template_includes_html_and_cta() -> None:
    message = AuthEmailService._build_password_reset_message(
        to_email="lara@test.dev",
        reset_url="https://app.nuvlystudio.com/reset-password?token=abc123",
        from_email="nuvlystudio@gmail.com",
        from_name="Nuvly",
    )

    assert message["Subject"] == "Restablece tu clave de Nuvly"
    assert message["To"] == "lara@test.dev"
    assert message["From"] == "Nuvly <nuvlystudio@gmail.com>"
    assert message.get_body(preferencelist=("plain",)) is not None
    html_part = message.get_body(preferencelist=("html",))
    assert html_part is not None
    html = html_part.get_content()
    assert "Crear nueva clave" in html
    assert "https://app.nuvlystudio.com/reset-password?token=abc123" in html
    assert "Nuvly" in html


def test_forgot_password_propagates_email_service_error() -> None:
    repository = InMemoryAuthRepository()
    service = AuthService(repository=repository, email_service=FailingAuthEmailService())
    service.register(
        RegisterRequest(
            email="lara@test.dev",
            confirmEmail="lara@test.dev",
            password="Supersecret1#",
            confirmPassword="Supersecret1#",
            name="Lara",
        )
    )

    with pytest.raises(NuvlyError) as exc:
        service.forgot_password(ForgotPasswordRequest(email="lara@test.dev"))

    assert exc.value.status_code == 502
    assert exc.value.code == "AUTH_EMAIL_SEND_FAILED"


def test_reset_password_changes_password_and_invalidates_token() -> None:
    repository = InMemoryAuthRepository()
    email_service = StubAuthEmailService()
    service = AuthService(repository=repository, email_service=email_service)
    service.register(
        RegisterRequest(
            email="lara@test.dev",
            confirmEmail="lara@test.dev",
            password="Supersecret1#",
            confirmPassword="Supersecret1#",
            name="Lara",
        )
    )
    service.forgot_password(ForgotPasswordRequest(email="lara@test.dev"))
    reset_url = email_service.sent_messages[0]["reset_url"]
    token = reset_url.split("token=", 1)[1]

    response = service.reset_password(
        ResetPasswordRequest(
            token=token,
            password="Nuevaclave1#",
            confirmPassword="Nuevaclave1#",
        )
    )

    assert response["ok"] is True
    with pytest.raises(NuvlyError) as used_exc:
        service.reset_password(
            ResetPasswordRequest(
                token=token,
                password="OtraClave1#",
                confirmPassword="OtraClave1#",
            )
        )
    assert used_exc.value.code == "INVALID_RESET_TOKEN"

    with pytest.raises(NuvlyError):
        service.login(LoginRequest(email="lara@test.dev", password="Supersecret1#"))

    new_session = service.login(LoginRequest(email="lara@test.dev", password="Nuevaclave1#"))
    assert new_session["user"]["email"] == "lara@test.dev"


def test_reset_password_rejects_password_that_does_not_match_policy() -> None:
    with pytest.raises(ValueError):
        ResetPasswordRequest(
            token="x" * 32,
            password="sinmayusculas1#",
            confirmPassword="sinmayusculas1#",
        )


def test_auth_routes_are_registered_in_openapi() -> None:
    paths = main_module.app.openapi()["paths"]

    assert "/api/auth/login" in paths
    assert "post" in paths["/api/auth/login"]
    assert "/api/admin/auth/login" in paths
    assert "post" in paths["/api/admin/auth/login"]
    assert "/api/auth/me" in paths
    assert "get" in paths["/api/auth/me"]
    assert "/api/auth/logout" in paths
    assert "post" in paths["/api/auth/logout"]
    assert "/api/auth/forgot-password" in paths
    assert "post" in paths["/api/auth/forgot-password"]
    assert "/api/auth/reset-password" in paths
    assert "post" in paths["/api/auth/reset-password"]


def test_ensure_internal_user_creates_required_nuvly_account() -> None:
    repository = InMemoryAuthRepository()
    service = AuthService(repository=repository)

    user = service.ensure_internal_user(email="nuvlystudio@gmail.com", password="Admin.1234")

    assert user["email"] == "nuvlystudio@gmail.com"
    assert user["accountType"] == "internal"
    assert user["internalRole"] == "admin"
    response = service.login_internal(LoginRequest(email="nuvlystudio@gmail.com", password="Admin.1234"))
    assert response["user"]["email"] == "nuvlystudio@gmail.com"


def test_ensure_internal_user_upgrades_existing_email_to_internal() -> None:
    repository = InMemoryAuthRepository()
    service = AuthService(repository=repository)
    service.register(
        RegisterRequest(
            email="nuvlystudio@gmail.com",
            confirmEmail="nuvlystudio@gmail.com",
            password="Cliente.1234",
            confirmPassword="Cliente.1234",
            name="Cliente",
        )
    )

    user = service.ensure_internal_user(email="nuvlystudio@gmail.com", password="Admin.1234")

    assert user["accountType"] == "internal"
    assert user["internalRole"] == "admin"
    response = service.login_internal(LoginRequest(email="nuvlystudio@gmail.com", password="Admin.1234"))
    assert response["authScope"] == "internal"


def test_create_internal_user_creates_developer_account() -> None:
    repository = InMemoryAuthRepository()
    service = AuthService(repository=repository)

    user = service.create_internal_user(
        email="dev@nuvly.dev",
        password="Devpass1#",
        name="Dev Uno",
        internal_role="developer",
    )

    assert user["accountType"] == "internal"
    assert user["internalRole"] == "developer"
    response = service.login_internal(LoginRequest(email="dev@nuvly.dev", password="Devpass1#"))
    assert response["user"]["internalRole"] == "developer"


def test_get_current_admin_user_rejects_developer_role(monkeypatch) -> None:
    monkeypatch.setattr(
        auth_dependencies.service,
        "get_user_from_token",
        lambda token, required_account_type=None: {
            "id": "usr_dev",
            "email": "dev@nuvly.dev",
            "accountType": "internal",
            "internalRole": "developer",
        },
    )

    with pytest.raises(NuvlyError) as exc:
        auth_dependencies.get_current_admin_user("Bearer test-token")

    assert exc.value.status_code == 403
    assert exc.value.code == "ADMIN_ROLE_REQUIRED"
