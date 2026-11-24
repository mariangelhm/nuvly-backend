from copy import deepcopy

import pytest
from test_payments_flow import InMemoryDomainRepository, _create_customer_project

from app.core.errors import NuvlyError
from app.modules.domain.schemas import CustomerWebsiteUpdate
from app.modules.domain.services import CUSTOMER_WEBSITE_CONFIG, CustomerProjectService


def website(status="published"):
    repo = InMemoryDomainRepository()
    project = _create_customer_project(repo)
    project.update(ownerId="owner", ownerEmail="owner@example.test")
    project["payment"] = {
        "status": "paid",
        "testMode": True,
        "paymentId": "pay_original",
        "finalUrl": f"http://localhost:5173/{project['id']}/{project['publicSlug']}",
    }
    repo.replace_document(CUSTOMER_WEBSITE_CONFIG.collection, project["id"], project, "missing", "missing", "duplicate")
    service = CustomerProjectService(CUSTOMER_WEBSITE_CONFIG, repository=repo)
    if status == "published":
        service.publish(project["id"])
    else:
        repo.update_document_fields(
            CUSTOMER_WEBSITE_CONFIG.collection, project["id"], {"customerStatus": status}, "missing", "missing"
        )
    return repo, service, service.get(project["id"])


def save(service, project, visible, pages_only=False):
    blocks = deepcopy(project["blocks"])
    blocks[0]["enabled"] = visible
    content = {"blocks": blocks}
    if pages_only:
        pages = deepcopy(project["pages"])
        pages[0]["blocks"] = blocks
        content = {"pages": pages}
    return service.update_for_owner(
        project["id"],
        CustomerWebsiteUpdate(
            title=project["title"],
            expectedUpdatedAt=project["updatedAt"],
            saveAsDraft=False,
            **content,
        ),
        owner_id="owner",
    )


@pytest.mark.parametrize("pages_only", [False, True])
def test_save_updates_visibility_in_public_snapshot_and_preserves_url_and_payment(pages_only):
    repo, service, project = website()
    original = service.get_published_by_slug(project["publicSlug"])
    saved = save(service, project, False, pages_only)
    public = service.get_published_by_slug(project["publicSlug"])
    assert public["version"] == original["version"] + 1
    assert public["id"] == saved["publishedSnapshotId"] != original["id"]
    assert public["snapshot"]["blocks"][0]["enabled"] is False
    assert public["snapshot"]["pages"][0]["blocks"][0]["enabled"] is False
    assert public["snapshot"]["pages"] == saved["pages"]
    assert saved["customerStatus"] == "published"
    for field in ("publicSlug", "payment", "firstPublishedAt", "statusHistory"):
        assert saved[field] == project[field]
    previous = repo.find_document(CUSTOMER_WEBSITE_CONFIG.snapshot_collection, {"id": original["id"]})
    assert previous["snapshot"]["blocks"][0]["enabled"] is True
    save(service, saved, True)
    assert service.get_published_by_slug(project["publicSlug"])["snapshot"]["blocks"][0]["enabled"] is True


@pytest.mark.parametrize("status", ["draft", "pending_payment", "payment_failed", "paid"])
def test_saving_unpublished_website_does_not_publish_it(status):
    repo, service, project = website(status)
    saved = save(service, project, False)
    assert saved["customerStatus"] == status
    assert not saved.get("publishedSnapshotId")
    assert repo.count_documents(CUSTOMER_WEBSITE_CONFIG.snapshot_collection, {"sourceId": project["id"]}) == 0


def test_failed_publication_does_not_report_saved_or_change_previous_public_version(monkeypatch):
    repo, service, project = website()
    original = service.get_published_by_slug(project["publicSlug"])
    insert = repo.insert_document

    def fail_snapshot(collection, *args, **kwargs):
        if collection == CUSTOMER_WEBSITE_CONFIG.snapshot_collection:
            raise RuntimeError("Snapshot storage unavailable")
        return insert(collection, *args, **kwargs)

    monkeypatch.setattr(repo, "insert_document", fail_snapshot)
    with pytest.raises(RuntimeError):
        save(service, project, False)
    assert service.get_published_by_slug(project["publicSlug"]) == original
    assert service.get(project["id"])["blocks"][0]["enabled"] is True


def test_other_customer_cannot_update_a_published_website():
    repo, service, project = website()
    with pytest.raises(NuvlyError) as error:
        service.update_for_owner(project["id"], CustomerWebsiteUpdate(title="Otra web"), owner_id="other")
    assert error.value.code == "CUSTOMER_PROJECT_FORBIDDEN"
    assert repo.count_documents(CUSTOMER_WEBSITE_CONFIG.snapshot_collection, {"sourceId": project["id"]}) == 1
