import json
from types import SimpleNamespace

import pytest

from app.operations import staging_validation as validation


def settings(**overrides):
    return SimpleNamespace(
        **{
            "app_env": "development",
            "payments_environment": "integration",
            "payments_production_enabled": False,
            "mongodb_db_name": "existing_database",
            "media_storage_durable": False,
            "public_base_url": None,
            "frontend_public_base_url": None,
            "api_prefix": "/api",
            **overrides,
        }
    )


@pytest.mark.parametrize(
    "name", ["production", "existing_database", "nuvly_validation_short", "nuvly_validation_../../data"]
)
def test_fixture_runner_rejects_nonisolated_targets_before_any_database_call(name):
    with pytest.raises(ValueError):
        validation.exercise_isolated_database(settings(), object(), name)


@pytest.mark.parametrize(
    "overrides",
    [{"app_env": "production"}, {"payments_environment": "production"}, {"payments_production_enabled": True}],
)
def test_fixture_runner_rejects_production_modes_before_any_database_call(overrides):
    with pytest.raises(ValueError):
        validation.exercise_isolated_database(settings(**overrides), object(), "nuvly_validation_20261124_abc")


def test_existing_validation_database_is_never_overwritten():
    client = SimpleNamespace(list_database_names=lambda: ["nuvly_validation_20261124_abc"])
    with pytest.raises(ValueError, match="VALIDATION_DATABASE_ALREADY_EXISTS"):
        validation.exercise_isolated_database(settings(), client, "nuvly_validation_20261124_abc")


def test_failed_connection_retains_configuration_evidence_and_redacts_exception(monkeypatch):
    def fail(_):
        raise OSError("mongodb://username:password@private-host")

    monkeypatch.setattr(validation, "connect", fail)
    result = validation.read_only_report(settings())
    assert result["phaseComplete"] is False
    assert result["checks"]["stagingIdentity"]["status"] == "blocked"
    assert result["checks"]["mongoTls"] == {"status": "blocked", "errorType": "OSError"}
    assert "password" not in json.dumps(result) and "private-host" not in json.dumps(result)


def test_index_permissions_failure_does_not_erase_successful_tls_evidence():
    class Client:
        admin = SimpleNamespace(command=lambda _: {"ok": 1})

        def __getitem__(self, name):
            raise PermissionError("private connection details")

    result = validation.read_only_report(settings(), Client())
    assert result["checks"]["mongoTls"]["status"] == "passed"
    assert result["checks"]["customerProductIndex"]["status"] == "blocked"
    assert result["phaseComplete"] is False


def test_explain_requires_the_compound_index_in_the_winning_plan():
    explain = {
        "ok": 1,
        "queryPlanner": {
            "winningPlan": {"stage": "COLLSCAN"},
            "rejectedPlans": [{"indexName": "ownerId_1_updatedAt_-1_id_1"}],
        },
    }
    assert validation.summarize_explain(explain)["status"] == "failed"
    explain["queryPlanner"]["winningPlan"] = {
        "stage": "FETCH",
        "inputStage": {"indexName": "ownerId_1_updatedAt_-1_id_1"},
    }
    assert validation.summarize_explain(explain)["status"] == "passed"


def test_health_error_bodies_are_never_recorded(monkeypatch):
    class Session:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def get(self, *args, **kwargs):
            assert kwargs["allow_redirects"] is False
            return SimpleNamespace(
                status_code=503, headers={"content-type": "application/json"}, json=lambda: {"error": "secret"}
            )

    monkeypatch.setattr(validation.requests, "Session", Session)
    result = validation.check_http("https://staging.test/api/health")
    assert result["status"] == "failed"
    assert "secret" not in json.dumps(result)


def test_data_audit_summary_never_prints_document_identifiers(capsys):
    from scripts.audit_data_contracts import run

    class Database:
        def __getitem__(self, name):
            return SimpleNamespace(
                find=lambda *args: [{"id": "private-project-id", "amount": 1.5}] if name == "payments" else []
            )

    assert run(Database(), summary_only=True) == 1
    output = capsys.readouterr().out
    assert "private-project-id" not in output
    assert json.loads(output)["issuesByCode"] == {"INVALID_CLP_AMOUNT": 1}
