from copy import deepcopy

import pytest
from test_payments_flow import InMemoryDomainRepository, _create_customer_project

from app.modules.domain.schemas import CustomerWebsiteUpdate
from app.modules.domain.services import CUSTOMER_WEBSITE_CONFIG, CustomerProjectService


@pytest.mark.parametrize("status", ["draft", "pending_payment", "paid", "published"])
@pytest.mark.parametrize("public_slug", [None, "direccion-elegida"])
def test_saving_progress_preserves_url_payment_and_publication_state(status, public_slug):
    repository = InMemoryDomainRepository()
    project = _create_customer_project(repository)
    project.update(
        publicSlug=public_slug,
        customerStatus=status,
        firstPublishedAt="2025-11-01T12:00:00Z",
        subscription={"nextRenewalAt": "2026-12-01T12:00:00Z"},
    )
    repository.replace_document(
        CUSTOMER_WEBSITE_CONFIG.collection, project["id"], project, "missing", "missing", "duplicate"
    )
    original_payment = deepcopy(project["payment"])
    updated = CustomerProjectService(CUSTOMER_WEBSITE_CONFIG, repository=repository).update(
        project["id"],
        CustomerWebsiteUpdate(title="Trabajo en curso", saveAsDraft=True),
    )
    stored = repository.find_document(CUSTOMER_WEBSITE_CONFIG.collection, {"id": project["id"]})
    assert updated["title"] == "Trabajo en curso"
    assert stored["publicSlug"] == public_slug
    assert stored["customerStatus"] == status
    assert stored["payment"] == original_payment
    assert stored.get("publishedSnapshotId") == project.get("publishedSnapshotId")
    assert stored["firstPublishedAt"] == project["firstPublishedAt"]
    assert stored["subscription"] == project["subscription"]
    assert "saveAsDraft" not in stored
    assert repository.find_document("payments", {"projectId": project["id"]}) is None


def test_republishing_preserves_first_publication_date(monkeypatch):
    repository = InMemoryDomainRepository()
    project = _create_customer_project(repository)
    project["payment"] = {"status": "paid", "testMode": True}
    repository.replace_document(
        CUSTOMER_WEBSITE_CONFIG.collection, project["id"], project, "missing", "missing", "duplicate"
    )
    service = CustomerProjectService(CUSTOMER_WEBSITE_CONFIG, repository=repository)
    monkeypatch.setattr("app.modules.domain.customer_project_service.utc_now_iso", lambda: "2026-11-01T12:00:00Z")
    service.publish(project["id"])
    monkeypatch.setattr("app.modules.domain.customer_project_service.utc_now_iso", lambda: "2026-11-13T12:00:00Z")
    service.publish(project["id"])
    stored = repository.find_document(CUSTOMER_WEBSITE_CONFIG.collection, {"id": project["id"]})
    assert stored["firstPublishedAt"] == "2026-11-01T12:00:00Z"
    assert stored["lastPublishedAt"] == "2026-11-13T12:00:00Z"


def test_paid_published_site_keeps_previous_public_version_when_saving_draft():
    from test_published_website_updates import website

    repo, service, project = website()
    public_before = service.get_published_by_slug(project["publicSlug"])
    count_before = repo.count_documents(CUSTOMER_WEBSITE_CONFIG.snapshot_collection, {"sourceId": project["id"]})
    service.update_for_owner(
        project["id"],
        CustomerWebsiteUpdate(title="Borrador privado", saveAsDraft=True, expectedUpdatedAt=project["updatedAt"]),
        owner_id="owner",
    )
    assert service.get_for_owner(project["id"], owner_id="owner")["title"] == "Borrador privado"
    assert service.get_published_by_slug(project["publicSlug"]) == public_before
    assert (
        repo.count_documents(CUSTOMER_WEBSITE_CONFIG.snapshot_collection, {"sourceId": project["id"]}) == count_before
    )
