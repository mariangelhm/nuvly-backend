from types import SimpleNamespace

import pytest
from test_auth_service import InMemoryAuthRepository

from app.modules.auth.schemas import LoginRequest
from app.modules.auth.service import AuthService
from scripts import create_internal_admin as command


@pytest.fixture
def provisioning(monkeypatch):
    repository = InMemoryAuthRepository()
    service = AuthService(repository=repository)
    monkeypatch.setattr(command, "AuthService", lambda: service)
    monkeypatch.setattr(command, "close_database", lambda: None)
    monkeypatch.setattr(command.sys, "stdin", SimpleNamespace(isatty=lambda: True))
    return repository, service


def passwords(monkeypatch, *values):
    responses = iter(values)
    monkeypatch.setattr(command.getpass, "getpass", lambda prompt: next(responses))


def test_operator_can_create_new_admin_without_printing_secret(provisioning, monkeypatch, capsys):
    repository, service = provisioning
    secret = "Provision1#"
    passwords(monkeypatch, secret, secret)
    assert command.main(["--email", "operator@example.test", "--name", "Operator"]) == 0
    assert len(repository.users) == 1
    assert (
        service.login_internal(LoginRequest(email="operator@example.test", password=secret))["user"]["internalRole"]
        == "admin"
    )
    captured = capsys.readouterr()
    assert secret not in captured.out + captured.err


@pytest.mark.parametrize(
    "email,name,first,second",
    [
        ("operator@example.test", "Operator", "Provision1#", "Different1#"),
        ("operator@example.test", "Operator", "weak", "weak"),
        ("invalid", "Operator", "Provision1#", "Provision1#"),
        ("operator@example.test", "   ", "Provision1#", "Provision1#"),
    ],
)
def test_invalid_provisioning_does_not_write_or_reveal_secret(
    provisioning, monkeypatch, capsys, email, name, first, second
):
    repository, _ = provisioning
    passwords(monkeypatch, first, second)
    assert command.main(["--email", email, "--name", name]) == 1
    assert repository.users == []
    captured = capsys.readouterr()
    assert first not in captured.out + captured.err
    assert second not in captured.out + captured.err


def test_noninteractive_input_is_rejected_before_provisioning(provisioning, monkeypatch):
    repository, _ = provisioning
    monkeypatch.setattr(command.sys, "stdin", SimpleNamespace(isatty=lambda: False))
    assert command.main(["--email", "operator@example.test", "--name", "Operator"]) == 1
    assert repository.users == []


def test_provisioning_repeat_does_not_reset_admin_password(provisioning, monkeypatch):
    repository, service = provisioning
    passwords(monkeypatch, "Provision1#", "Provision1#", "Replacement1#", "Replacement1#")
    args = ["--email", "operator@example.test", "--name", "Operator"]
    assert command.main(args) == 0
    repository.users[0]["active"] = False
    original = repository.users[0].copy()
    assert command.main(args) == 1
    assert len(repository.users) == 1
    assert repository.users[0] == original
    assert service._verify_password("Provision1#", original["providerLinks"]["nuvly"]["passwordHash"])
