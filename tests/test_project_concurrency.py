from types import SimpleNamespace

import pytest
from test_payments_flow import InMemoryDomainRepository, _create_customer_project
from test_published_website_updates import website

from app.core.errors import NuvlyError
from app.modules.domain.repository import DomainRepository
from app.modules.domain.schemas import CustomerWebsiteUpdate
from app.modules.domain.services import CUSTOMER_WEBSITE_CONFIG, CustomerProjectService


def test_two_client_drafts_with_same_version_cannot_overwrite_each_other():
    repo = InMemoryDomainRepository()
    project = _create_customer_project(repo)
    project["ownerId"] = "owner"
    repo.replace_document(CUSTOMER_WEBSITE_CONFIG.collection, project["id"], project, "missing", "missing", "duplicate")
    service = CustomerProjectService(CUSTOMER_WEBSITE_CONFIG, repository=repo)
    first = CustomerWebsiteUpdate(title="First tab", saveAsDraft=True, expectedUpdatedAt=project["updatedAt"])
    stale = CustomerWebsiteUpdate(title="Stale tab", saveAsDraft=True, expectedUpdatedAt=project["updatedAt"])
    service.update_for_owner(project["id"], first, owner_id="owner")
    with pytest.raises(NuvlyError) as exc:
        service.update_for_owner(project["id"], stale, owner_id="owner")
    assert exc.value.code == "PROJECT_VERSION_CONFLICT"
    assert service.get(project["id"])["title"] == "First tab"
    with pytest.raises(NuvlyError) as exc:
        service.update_for_owner(project["id"], CustomerWebsiteUpdate(title="No version"), owner_id="owner")
    assert exc.value.status_code == 428


def test_publication_conflict_removes_only_its_unattached_snapshot(monkeypatch):
    repo, service, project = website()
    old_public = service.get_published_by_slug(project["publicSlug"])
    replace = repo.replace_document

    def concurrent(collection, identifier, document, *args, **kwargs):
        if collection == CUSTOMER_WEBSITE_CONFIG.collection:
            repo.update_document_fields(
                collection, identifier, {"updatedAt": "concurrent", "title": "Concurrent edit"}, "missing", "missing"
            )
        return replace(collection, identifier, document, *args, **kwargs)

    monkeypatch.setattr(repo, "replace_document", concurrent)
    with pytest.raises(NuvlyError) as exc:
        service.publish(project["id"])
    assert exc.value.code == "PROJECT_VERSION_CONFLICT"
    assert service.get_published_by_slug(project["publicSlug"]) == old_public
    assert service.get(project["id"])["title"] == "Concurrent edit"
    assert repo.count_documents(CUSTOMER_WEBSITE_CONFIG.snapshot_collection, {"sourceId": project["id"]}) == 1


def test_mongo_replace_uses_atomic_version_filter(monkeypatch):
    class Collection:
        def replace_one(self, filters, document):
            self.filters = filters
            return SimpleNamespace(matched_count=0)

    collection = Collection()
    repo = DomainRepository()
    monkeypatch.setattr(repo, "collection", lambda name: collection)
    with pytest.raises(NuvlyError) as exc:
        repo.replace_document(
            "customer_websites",
            "project",
            {"title": "new"},
            "missing",
            "missing",
            "duplicate",
            expected_updated_at="version-one",
        )
    assert collection.filters == {"id": "project", "updatedAt": "version-one"}
    assert exc.value.status_code == 409
