import pytest
from test_payments_flow import InMemoryDomainRepository, _create_customer_project

from app.core.errors import NuvlyError
from app.modules.domain.schemas import CustomerWebsiteUpdate
from app.modules.domain.services import CUSTOMER_WEBSITE_CONFIG, CustomerProjectService


@pytest.mark.parametrize("operation", ["get", "update", "publish"])
def test_email_match_never_overrides_another_owner_id(operation):
    repo = InMemoryDomainRepository()
    project = _create_customer_project(repo)
    project["ownerId"] = "owner-a"
    repo.replace_document(CUSTOMER_WEBSITE_CONFIG.collection, project["id"], project, "missing", "missing", "duplicate")
    service = CustomerProjectService(CUSTOMER_WEBSITE_CONFIG, repository=repo)
    kwargs = {"owner_id": "owner-b", "owner_email": project["ownerEmail"]}
    with pytest.raises(NuvlyError) as exc:
        if operation == "get":
            service.get_for_owner(project["id"], **kwargs)
        elif operation == "update":
            service.update_for_owner(project["id"], CustomerWebsiteUpdate(title="Attack"), **kwargs)
        else:
            service.publish_for_owner(project["id"], **kwargs)
    assert exc.value.code == "CUSTOMER_PROJECT_FORBIDDEN"
    assert service.list_by_owner(**kwargs) == []


def test_legacy_claim_requires_verified_email_and_only_claims_unowned_project(monkeypatch):
    repo = InMemoryDomainRepository()
    project = _create_customer_project(repo)
    service = CustomerProjectService(CUSTOMER_WEBSITE_CONFIG, repository=repo)

    def claim(collection, identifier, old_email, owner_id, email):
        current = repo.find_document(collection, {"id": identifier, "ownerId": None, "ownerEmail": old_email})
        assert current is not None
        return repo.update_document_fields(
            collection, identifier, {"ownerId": owner_id, "ownerEmail": email}, "missing", "missing"
        )

    monkeypatch.setattr(repo, "claim_customer_project", claim, raising=False)
    user = {"id": "owner-a", "email": project["ownerEmail"], "emailVerified": False}
    with pytest.raises(NuvlyError) as exc:
        service.claim_for_verified_owner(project["id"], user)
    assert exc.value.code == "VERIFIED_EMAIL_REQUIRED"
    user["emailVerified"] = True
    assert service.claim_for_verified_owner(project["id"], user)["ownerId"] == "owner-a"
    assert service.get_for_owner(project["id"], owner_id="owner-a")["id"] == project["id"]
    with pytest.raises(NuvlyError):
        service.claim_for_verified_owner(project["id"], {**user, "id": "owner-b"})
