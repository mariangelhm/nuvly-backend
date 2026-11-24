import asyncio
import json

import pytest
from fastapi import FastAPI
from starlette.requests import Request
from test_auth_service import InMemoryAuthRepository, StubAuthEmailService

from app.core.config import get_settings
from app.core.errors import NuvlyError, register_exception_handlers
from app.core.security_headers import SecurityHeadersMiddleware
from app.modules.auth import dependencies, routes
from app.modules.auth.schemas import ForgotPasswordRequest, RegisterRequest, ResetPasswordRequest
from app.modules.auth.service import AuthService
from app.modules.health import routes as health


def request(method="POST", **headers):
    return Request(
        {
            "type": "http",
            "method": method,
            "path": "/api/auth/logout",
            "headers": [(key.replace("_", "-").encode(), value.encode()) for key, value in headers.items()],
        }
    )


def exchange(app, method, path, headers=None, body=None):
    async def run():
        messages = []

        async def receive():
            return {"type": "http.request", "body": json.dumps(body or {}).encode(), "more_body": False}

        async def send(message):
            messages.append(message)

        await app(
            {
                "type": "http",
                "asgi": {"version": "3.0"},
                "http_version": "1.1",
                "scheme": "https",
                "method": method,
                "path": path,
                "raw_path": path.encode(),
                "query_string": b"",
                "root_path": "",
                "server": ("api.test", 443),
                "client": ("test", 1),
                "headers": [
                    (k.encode(), v.encode()) for k, v in {"content-type": "application/json", **(headers or {})}.items()
                ],
            },
            receive,
            send,
        )
        start = next(m for m in messages if m["type"] == "http.response.start")
        return start["status"], dict(start["headers"]), json.loads(b"".join(m.get("body", b"") for m in messages))

    return asyncio.run(run())


@pytest.fixture
def auth_app(monkeypatch):
    service = AuthService(InMemoryAuthRepository())
    service.register(
        RegisterRequest(
            email="client@example.test",
            confirmEmail="client@example.test",
            password="Original1#",
            confirmPassword="Original1#",
            name="Client",
        )
    )
    service.create_internal_user(email="admin@example.test", password="Original1#", name="Admin", internal_role="admin")
    monkeypatch.setattr(routes, "service", service)
    monkeypatch.setattr(dependencies, "service", service)
    monkeypatch.setattr(routes, "consume_rate_limit", lambda *args: None)
    monkeypatch.setattr(get_settings(), "cors_origins", "https://front.test")
    monkeypatch.setattr(get_settings(), "app_env", "production")
    app = FastAPI()
    register_exception_handlers(app)
    app.add_middleware(SecurityHeadersMiddleware, api_prefix="/api")
    app.include_router(routes.router, prefix="/api")
    app.include_router(routes.admin_router, prefix="/api")
    return app, service


HEADERS = {"origin": "https://front.test", "x-nuvly-session-mode": "cookie", "x-nuvly-auth-scope": "customer"}


def test_browser_login_me_logout_and_scope_isolation(auth_app):
    app, service = auth_app
    status, headers, payload = exchange(
        app, "POST", "/api/auth/login", HEADERS, {"email": "client@example.test", "password": "Original1#"}
    )
    assert status == 200 and payload["token"] == "" and payload["sessionKind"] == "cookie"
    cookie = headers[b"set-cookie"].decode()
    assert "HttpOnly" in cookie and "Secure" in cookie and "SameSite=none" in cookie
    assert "Domain=" not in cookie
    assert headers[b"cache-control"] == b"no-store"
    credentials = {**HEADERS, "cookie": cookie.split(";", 1)[0]}
    assert exchange(app, "GET", "/api/auth/me", credentials)[0] == 200
    assert exchange(app, "GET", "/api/auth/me", {**credentials, "x-nuvly-auth-scope": "internal"})[0] == 401
    assert exchange(app, "GET", "/api/auth/me", {"cookie": credentials["cookie"]})[0] == 401
    assert exchange(app, "POST", "/api/auth/logout", {**credentials, "origin": "https://evil.test"})[0] == 403
    status, headers, _ = exchange(app, "POST", "/api/auth/logout", credentials)
    assert status == 200 and "Max-Age=0" in headers[b"set-cookie"].decode()
    assert exchange(app, "GET", "/api/auth/me", credentials)[0] == 401


@pytest.mark.parametrize("origin", ["https://evil.test", "null", "https://front.test.evil.test", ""])
def test_untrusted_browser_login_creates_no_session(auth_app, origin):
    app, service = auth_app
    count = len(service.repository.sessions)
    status, headers, _ = exchange(
        app,
        "POST",
        "/api/auth/login",
        {**HEADERS, "origin": origin},
        {"email": "client@example.test", "password": "Original1#"},
    )
    assert status == 403 and b"set-cookie" not in headers
    assert len(service.repository.sessions) == count


def test_internal_cookie_and_bearer_api_clients_remain_separate(auth_app):
    app, _ = auth_app
    status, headers, payload = exchange(
        app,
        "POST",
        "/api/admin/auth/login",
        {**HEADERS, "x-nuvly-auth-scope": "internal"},
        {"email": "admin@example.test", "password": "Original1#"},
    )
    assert status == 200 and "nuvly_internal_session=" in headers[b"set-cookie"].decode()
    assert payload["token"] == ""
    status, headers, payload = exchange(
        app, "POST", "/api/auth/login", {}, {"email": "client@example.test", "password": "Original1#"}
    )
    assert status == 200 and payload["token"] and b"set-cookie" not in headers
    assert exchange(app, "GET", "/api/auth/me", {"authorization": "Bearer " + payload["token"]})[0] == 200


def test_password_reset_revokes_previous_sessions_and_cannot_reuse_token():
    repo, mail = InMemoryAuthRepository(), StubAuthEmailService()
    service = AuthService(repo, mail)
    session = service.register(
        RegisterRequest(
            email="client@example.test",
            confirmEmail="client@example.test",
            password="Original1#",
            confirmPassword="Original1#",
            name="Client",
        )
    )
    service.forgot_password(ForgotPasswordRequest(email="client@example.test"))
    token = mail.sent_messages[0]["reset_url"].split("token=", 1)[1]
    service.forgot_password(ForgotPasswordRequest(email="client@example.test"))
    other_token = mail.sent_messages[1]["reset_url"].split("token=", 1)[1]
    payload = ResetPasswordRequest(token=token, password="Replacement1#", confirmPassword="Replacement1#")
    service.reset_password(payload)
    with pytest.raises(NuvlyError, match="Sesion"):
        service.get_user_from_token(session["token"])
    with pytest.raises(NuvlyError):
        service.reset_password(payload)
    with pytest.raises(NuvlyError):
        service.reset_password(
            ResetPasswordRequest(token=other_token, password="Anotherpass1#", confirmPassword="Anotherpass1#")
        )


@pytest.mark.parametrize("startup,db_ok", [("ready", False), ("degraded", True), ("starting", True), ("ready", True)])
def test_public_health_is_ready_only_after_successful_startup_and_never_leaks(monkeypatch, startup, db_ok):
    def ping():
        if not db_ok:
            raise RuntimeError("mongodb://private:secret@private-host")

    monkeypatch.setattr(health, "ping_database", ping)
    app = FastAPI()
    app.state.startup_status = startup
    app.state.startup_error = "mongodb://private:secret@private-host"
    app.include_router(health.router, prefix="/api")
    status, _, payload = exchange(app, "GET", "/api/health")
    assert status == (200 if startup == "ready" and db_ok else 503)
    assert "error" not in payload and "secret" not in json.dumps(payload)


def test_startup_index_creation_never_drops_indexes(monkeypatch):
    from app.core import database

    class Collection:
        def create_index(self, *args, **kwargs):
            pass

        def drop_index(self, *args):
            pytest.fail("Startup must not drop indexes")

    class Database:
        def __getattr__(self, name):
            return Collection()

    monkeypatch.setattr(database, "get_database", Database)
    database.create_indexes()


@pytest.mark.parametrize(
    "stored", [None, "invalid", "pbkdf2_sha256$bad$a$b", "pbkdf2_sha256$999999999$a$b", "pbkdf2_sha256$1$!!!!$!!!!"]
)
def test_corrupt_password_hash_fails_closed(stored):
    assert AuthService._verify_password("password", stored) is False


def test_reset_token_claim_is_atomic_in_repository(monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Lock
    from types import SimpleNamespace

    from app.modules.auth.repository import AuthRepository

    lock = Lock()
    claimed = False

    class Collection:
        def update_one(self, query, update):
            nonlocal claimed
            assert query == {"id": "reset-id", "usedAt": None}
            with lock:
                if claimed:
                    return SimpleNamespace(modified_count=0)
                claimed = True
                return SimpleNamespace(modified_count=1)

    repo = AuthRepository()
    monkeypatch.setattr(repo, "collection", lambda name: Collection())
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: repo.consume_password_reset_token("reset-id", "now"), range(20)))
    assert sum(results) == 1


def test_explicit_index_migration_is_repeatable():
    import importlib.util
    from pathlib import Path

    spec = importlib.util.spec_from_file_location(
        "security_migration", Path(__file__).parents[1] / "scripts/migrate_security_indexes.py"
    )
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    class Collection:
        def __init__(self):
            self.indexes = {
                "slug_1": {"key": [("slug", 1)], "unique": True},
                "componentCode_1": {"key": [("componentCode", 1)], "unique": True},
            }
            self.dropped = []

        def index_information(self):
            return self.indexes.copy()

        def drop_index(self, name):
            self.dropped.append(name)
            del self.indexes[name]

        def create_index(self, keys, **options):
            self.indexes["_".join(f"{key}_{direction}" for key, direction in keys)] = {"key": keys, **options}

    db = {name: Collection() for name in ("customer_invitations", "customer_websites", "pricing_components")}
    assert len(migration.migrate(db)) == 3
    assert migration.migrate(db) == []


@pytest.mark.parametrize(
    "origin", ["*", "https://*.test", "https://front.test/path", "https://user:pass@front.test", "null", ""]
)
def test_cors_configuration_rejects_ambiguous_or_wildcard_origins(origin):
    from pydantic import ValidationError

    from app.core.config import Settings

    with pytest.raises(ValidationError):
        Settings(_env_file=None, MONGODB_URI="mongodb://offline", CORS_ORIGINS=origin, APP_ENV="test")


def test_production_configuration_requires_trusted_https_origins():
    from pydantic import ValidationError

    from app.core.config import Settings

    config = dict(
        _env_file=None,
        MONGODB_URI="mongodb://offline",
        APP_ENV="production",
        PUBLIC_BASE_URL="https://api.test",
        FRONTEND_PUBLIC_BASE_URL="https://front.test",
        CORS_ORIGINS="https://front.test",
    )
    assert Settings(**config).public_base_url == "https://api.test"
    with pytest.raises(ValidationError):
        Settings(**{**config, "PUBLIC_BASE_URL": "http://api.test"})
    with pytest.raises(ValidationError):
        Settings(**{**config, "CORS_ORIGINS": "https://other.test"})


def test_password_changed_during_login_cannot_restore_old_credentials(monkeypatch):
    from app.modules.auth.schemas import LoginRequest

    repo = InMemoryAuthRepository()
    service = AuthService(repo)
    service.register(
        RegisterRequest(
            email="race@example.test",
            confirmEmail="race@example.test",
            password="Original1#",
            confirmPassword="Original1#",
            name="Client",
        )
    )
    count = len(repo.sessions)
    original = service._verify_password

    def verify_and_rotate(password, stored_hash):
        result = original(password, stored_hash)
        repo.users[0]["credentialsVersion"] = "changed-during-verification"
        return result

    monkeypatch.setattr(service, "_verify_password", verify_and_rotate)
    with pytest.raises(NuvlyError) as error:
        service.login(LoginRequest(email="race@example.test", password="Original1#"))
    assert error.value.code == "INVALID_CREDENTIALS"
    assert len(repo.sessions) == count
    assert repo.users[0]["credentialsVersion"] == "changed-during-verification"
