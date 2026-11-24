import json
import time
from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from google.auth import crypt, jwt
from starlette.requests import Request as WebRequest
from test_auth_service import InMemoryAuthRepository

from app.core.config import get_settings
from app.core.errors import NuvlyError
from app.modules.auth import google_identity
from app.modules.auth import service as auth_module
from app.modules.auth.routes import require_google_origin
from app.modules.auth.schemas import GoogleLoginRequest, RegisterRequest
from app.modules.auth.service import AuthService


class GoogleRepository(InMemoryAuthRepository):
    def __init__(self):
        super().__init__()
        self.challenges = {}

    def insert_google_challenge(self, document):
        self.challenges[document["tokenHash"]] = deepcopy(document)

    def consume_google_challenge(self, token_hash, now):
        result = self.challenges.pop(token_hash, None)
        return result if result and result["expiresAt"] > now else None

    def find_user_by_google_subject(self, subject):
        return next(
            (
                deepcopy(user)
                for user in self.users
                if user.get("providerLinks", {}).get("google", {}).get("subject") == subject
            ),
            None,
        )


@pytest.fixture
def google_login(monkeypatch):
    monkeypatch.setattr(get_settings(), "google_client_id", "test.apps.googleusercontent.com")
    repository = GoogleRepository()
    service = AuthService(repository=repository)
    claims = {"sub": "google-user-1", "email": "lara@gmail.com", "name": "Lara", "email_verified": True}
    monkeypatch.setattr(auth_module, "verify_google_credential", lambda token, client_id: deepcopy(claims))

    def request():
        challenge = service.create_google_challenge()
        claims["nonce"] = challenge["nonce"]
        return GoogleLoginRequest(credential="signed-token", challengeToken=challenge["challengeToken"])

    return service, repository, claims, request


def register_local(service, email="lara@gmail.com"):
    return service.register(
        RegisterRequest(
            email=email, confirmEmail=email, password="Supersecret1#", confirmPassword="Supersecret1#", name="Lara"
        )
    )


def test_google_creates_customer_and_uses_nuvly_session(google_login):
    service, repository, claims, request = google_login
    response = service.login_google(request())
    assert response["authProvider"] == "google"
    assert response["authScope"] == "customer"
    assert response["user"]["emailVerified"] is True
    assert response["token"] != "signed-token"
    assert repository.users[0]["providerLinks"]["google"]["subject"] == claims["sub"]
    assert "passwordHash" not in repository.users[0]["providerLinks"]["google"]
    assert service.get_user_from_token(response["token"])["id"] == response["user"]["id"]
    assert repository.sessions[0]["tokenHash"] != response["token"]


def test_google_reuses_subject_even_after_google_email_changes(google_login):
    service, repository, claims, request = google_login
    first = service.login_google(request())
    claims["email"] = "changed@gmail.com"
    second = service.login_google(request())
    assert first["user"]["id"] == second["user"]["id"]
    assert len(repository.users) == 1


def test_google_links_verified_gmail_without_removing_password(google_login):
    service, repository, claims, request = google_login
    existing = register_local(service)
    password_hash = repository.users[0]["providerLinks"]["nuvly"]["passwordHash"]
    response = service.login_google(request())
    assert response["user"]["id"] == existing["user"]["id"]
    assert response["user"]["authProviders"] == ["nuvly", "google"]
    assert repository.users[0]["providerLinks"]["nuvly"]["passwordHash"] == password_hash


@pytest.mark.parametrize(
    "field,value",
    [("email_verified", False), ("email_verified", "true"), ("nonce", "wrong"), ("sub", ""), ("email", "invalid")],
)
def test_google_rejects_invalid_identity_claims(google_login, field, value):
    service, repository, claims, request = google_login
    payload = request()
    claims[field] = value
    with pytest.raises(NuvlyError) as exc:
        service.login_google(payload)
    assert exc.value.code == "INVALID_GOOGLE_CREDENTIAL"
    assert repository.users == []
    assert repository.sessions == []


def test_google_challenge_is_single_use(google_login):
    service, repository, claims, request = google_login
    payload = request()
    service.login_google(payload)
    with pytest.raises(NuvlyError) as exc:
        service.login_google(payload)
    assert exc.value.code == "GOOGLE_CHALLENGE_EXPIRED"
    assert len(repository.sessions) == 1


def test_google_expired_challenge_cannot_create_session(google_login):
    service, repository, claims, request = google_login
    payload = request()
    next(iter(repository.challenges.values()))["expiresAt"] = datetime.now(timezone.utc) - timedelta(seconds=1)
    with pytest.raises(NuvlyError) as exc:
        service.login_google(payload)
    assert exc.value.code == "GOOGLE_CHALLENGE_EXPIRED"
    assert repository.sessions == []


@pytest.mark.parametrize("account_type,active", [("internal", True), ("customer", False)])
def test_google_cannot_enter_internal_or_disabled_accounts(google_login, account_type, active):
    service, repository, claims, request = google_login
    register_local(service)
    repository.sessions.clear()
    repository.users[0].update(accountType=account_type, active=active)
    with pytest.raises(NuvlyError) as exc:
        service.login_google(request())
    assert exc.value.status_code == 403
    assert repository.sessions == []
    assert repository.users[0]["authProviders"] == ["nuvly"]


def test_google_cannot_silently_link_third_party_email(google_login):
    service, repository, claims, request = google_login
    register_local(service, "lara@example.com")
    claims["email"] = "lara@example.com"
    with pytest.raises(NuvlyError) as exc:
        service.login_google(request())
    assert exc.value.code == "GOOGLE_ACCOUNT_LINK_REQUIRED"


def test_google_workspace_email_can_link_existing_customer(google_login):
    service, repository, claims, request = google_login
    existing = register_local(service, "lara@example.com")
    claims.update(email="lara@example.com", hd="example.com")
    assert service.login_google(request())["user"]["id"] == existing["user"]["id"]


def test_google_missing_configuration_does_not_create_challenge(google_login, monkeypatch):
    service, repository, claims, request = google_login
    monkeypatch.setattr(get_settings(), "google_client_id", None)
    with pytest.raises(NuvlyError) as exc:
        service.create_google_challenge()
    assert exc.value.code == "GOOGLE_AUTH_NOT_CONFIGURED"
    assert repository.challenges == {}


@pytest.mark.parametrize(
    "origin,allowed", [("http://localhost:5173", True), ("https://evil.example", False), ("", False)]
)
def test_google_endpoints_restrict_browser_origin(monkeypatch, origin, allowed):
    monkeypatch.setattr(get_settings(), "cors_origins", "http://localhost:5173")
    request = WebRequest({"type": "http", "headers": [(b"origin", origin.encode())]})
    if allowed:
        require_google_origin(request)
    else:
        with pytest.raises(NuvlyError) as exc:
            require_google_origin(request)
        assert exc.value.status_code == 403


@pytest.fixture(scope="module")
def signing_keys():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "test-only")])
    now = datetime.now(timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(1)
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=1))
        .sign(key, hashes.SHA256())
    )
    private = key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    )
    return crypt.RSASigner.from_string(private, key_id="test-key"), cert.public_bytes(
        serialization.Encoding.PEM
    ).decode()


@pytest.mark.parametrize(
    "change,valid",
    [({}, True), ({"aud": "wrong-client"}, False), ({"iss": "https://evil.example"}, False), ({"exp": 1}, False)],
)
def test_official_google_verifier_checks_real_signature_audience_issuer_and_expiry(
    monkeypatch, signing_keys, change, valid
):
    signer, cert = signing_keys

    class Response:
        status = 200
        data = json.dumps({"test-key": cert}).encode()

    monkeypatch.setattr(google_identity, "Request", lambda: lambda url, **kwargs: Response())
    claims = {
        "iss": "https://accounts.google.com",
        "aud": "test-client",
        "sub": "test-user",
        "iat": int(time.time()) - 10,
        "exp": int(time.time()) + 300,
        **change,
    }
    token = jwt.encode(signer, claims).decode()
    if valid:
        assert google_identity.verify_google_credential(token, "test-client")["sub"] == "test-user"
        parts = token.split(".")
        parts[2] = ("A" if parts[2][0] != "A" else "B") + parts[2][1:]
        with pytest.raises(NuvlyError):
            google_identity.verify_google_credential(".".join(parts), "test-client")
    else:
        with pytest.raises(NuvlyError) as exc:
            google_identity.verify_google_credential(token, "test-client")
        assert exc.value.code == "INVALID_GOOGLE_CREDENTIAL"
