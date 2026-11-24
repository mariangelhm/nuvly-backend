from copy import deepcopy
from types import SimpleNamespace

import pytest
from test_payments_flow import InMemoryDomainRepository, _create_customer_project

from app.core.errors import NuvlyError
from app.modules.domain import customer_project_service as services
from app.modules.domain.services import CUSTOMER_WEBSITE_CONFIG, CustomerProjectService


@pytest.mark.parametrize("operation", ["publish", "status", "store"])
def test_unpaid_project_cannot_publish_by_any_service_path(operation):
    repo = InMemoryDomainRepository()
    project = _create_customer_project(repo)
    service = CustomerProjectService(CUSTOMER_WEBSITE_CONFIG, repository=repo)
    before = deepcopy(repo.collections)
    with pytest.raises(NuvlyError) as exc:
        if operation == "status":
            service.update_status(project["id"], "published", None, None)
        elif operation == "store":
            service._store_publication(project, "2026-11-14T00:00:00Z")
        else:
            service.publish(project["id"])
    assert exc.value.code == "PAYMENT_REQUIRED"
    assert repo.collections == before


@pytest.mark.parametrize(
    "environment,test_mode,allowed",
    [
        ("production", True, False),
        ("integration", False, False),
        ("production", False, True),
    ],
)
def test_production_never_accepts_test_entitlements(monkeypatch, environment, test_mode, allowed):
    monkeypatch.setattr(services, "get_settings", lambda: SimpleNamespace(app_env="production"))
    document = {"payment": {"status": "paid", "environment": environment, "testMode": test_mode}}
    if allowed:
        CustomerProjectService._assert_publication_entitlement(document)
    else:
        with pytest.raises(NuvlyError) as exc:
            CustomerProjectService._assert_publication_entitlement(document)
        assert exc.value.code == "TEST_PAYMENT_NOT_ALLOWED"
