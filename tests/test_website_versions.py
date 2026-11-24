import asyncio
import json
from copy import deepcopy
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from test_payments_flow import InMemoryDomainRepository, _create_customer_project

from app.core.errors import NuvlyError, register_exception_handlers
from app.modules.auth import dependencies
from app.modules.domain import studio_routes
from app.modules.domain.repository import DomainRepository
from app.modules.domain.schemas import CustomerWebsiteUpdate
from app.modules.domain.services import CUSTOMER_WEBSITE_CONFIG, CustomerProjectService
from app.modules.domain.website_versions import WebsiteVersionsService


class Repo(InMemoryDomainRepository):
    def list_admin_customer_websites(self, search, limit, skip):
        rows = [
            r
            for r in self.collections.get("customer_websites", [])
            if not search or search.lower() in str([r["id"], r["title"], r.get("ownerEmail")]).lower()
        ]
        return {"items": deepcopy(rows[skip : skip + limit]), "total": len(rows)}

    def restore_customer_website(self, project_id, expected_snapshot_id, changes, event, *, expected_updated_at=None):
        current = self.find_document("customer_websites", {"id": project_id})
        if (
            current["publishedSnapshotId"] != expected_snapshot_id
            or current["customerStatus"] != "published"
            or current["payment"]["status"] != "paid"
            or (expected_updated_at is not None and current.get("updatedAt") != expected_updated_at)
        ):
            raise NuvlyError("La web cambió", 409, "WEBSITE_VERSION_CONFLICT")
        current.update(deepcopy(changes))
        current["statusHistory"].append(deepcopy(event))
        return self.replace_document("customer_websites", project_id, current, "missing", "missing", "duplicate")

    def discard_unpublished_restore_snapshot(self, snapshot_id):
        self.collections["customer_website_snapshots"] = [
            s for s in self.collections["customer_website_snapshots"] if s["id"] != snapshot_id
        ]


@pytest.fixture
def site():
    repo = Repo()
    p = _create_customer_project(repo)
    p.update(
        ownerId="customer",
        ownerEmail="client@example.test",
        formSubmissions=[{"id": "lead-current"}],
        leadForms=[{"id": "form-current"}],
        subscription={"validUntil": "2027-11-13"},
    )
    p["payment"] = {
        "status": "paid",
        "testMode": True,
        "paymentId": "original-payment",
        "finalUrl": "https://client.test/mi-web",
    }
    repo.replace_document("customer_websites", p["id"], p, "missing", "missing", "duplicate")
    projects = CustomerProjectService(CUSTOMER_WEBSITE_CONFIG, repository=repo)
    original = projects.publish(p["id"])
    projects.update(
        p["id"],
        CustomerWebsiteUpdate(title="Versión dañada", saveAsDraft=False, blocks=[{**p["blocks"][0], "enabled": False}]),
    )
    return repo, projects, WebsiteVersionsService(repo), original


ACTOR = {"id": "admin-1", "name": "Admin Nuvly", "internalRole": "admin"}


class ApiClient:
    """Exercise the real ASGI router without extra HTTP client dependencies."""

    def __init__(self, app):
        self.app = app

    def request(self, method, url, body=None):
        async def run():
            path, _, query = url.partition("?")
            sent = []

            async def receive():
                return {
                    "type": "http.request",
                    "body": json.dumps(body).encode() if body is not None else b"",
                    "more_body": False,
                }

            async def send(message):
                sent.append(message)

            await self.app(
                {
                    "type": "http",
                    "asgi": {"version": "3.0"},
                    "http_version": "1.1",
                    "method": method,
                    "scheme": "http",
                    "path": path,
                    "raw_path": path.encode(),
                    "query_string": query.encode(),
                    "root_path": "",
                    "headers": [(b"content-type", b"application/json")],
                    "server": ("test", 80),
                    "client": ("test", 123),
                },
                receive,
                send,
            )
            status = next(item["status"] for item in sent if item["type"] == "http.response.start")
            payload = b"".join(item.get("body", b"") for item in sent if item["type"] == "http.response.body")
            return SimpleNamespace(status_code=status, json=lambda: json.loads(payload))

        return asyncio.run(run())

    def get(self, url):
        return self.request("GET", url)

    def post(self, url, json):
        return self.request("POST", url, json)


def test_restore_updates_editor_and_public_site_and_preserves_operational_data(site):
    repo, projects, service, original = site
    before = projects.get(original["sourceId"])
    current_snapshot = before["publishedSnapshotId"]
    result = service.restore(
        before["id"], original["id"], current_snapshot, ACTOR, "  Cliente pidió recuperar la página  "
    )
    after = projects.get(before["id"])
    assert result["version"] == 3 and result["restoredFromVersion"] == 1
    assert after["blocks"][0]["enabled"] is True
    assert after["pages"][0]["blocks"][0]["enabled"] is True
    assert after["title"] == original["snapshot"]["title"]
    public = projects.get_published_by_slug(before["publicSlug"])
    assert public["snapshot"]["blocks"] == after["blocks"]
    assert public["id"] == after["publishedSnapshotId"] == result["snapshotId"]
    for key in (
        "id",
        "publicSlug",
        "slug",
        "ownerId",
        "ownerEmail",
        "payment",
        "planTier",
        "templateId",
        "templateSnapshotId",
        "firstPublishedAt",
        "subscription",
        "formSubmissions",
        "leadForms",
        "customerData",
    ):
        assert after[key] == before[key], key
    assert after["statusHistory"][-1]["changedBy"] == ACTOR["id"]
    assert after["statusHistory"][-1]["restoration"]["note"] == "Cliente pidió recuperar la página"
    damaged = repo.find_document("customer_website_snapshots", {"id": current_snapshot})
    assert damaged["snapshot"]["blocks"][0]["enabled"] is False
    history = service.history(before["id"])
    assert [item["version"] for item in history["items"]] == [3, 2, 1]
    assert history["items"][0]["restoration"]["actorName"] == ACTOR["name"]
    assert history["items"][0]["isCurrent"] and not history["items"][1]["isCurrent"]


def test_can_restore_the_damaged_version_again_without_losing_history(site):
    repo, projects, service, original = site
    before = projects.get(original["sourceId"])
    damaged_id = before["publishedSnapshotId"]
    restored = service.restore(before["id"], original["id"], damaged_id, ACTOR)
    service.restore(before["id"], damaged_id, restored["snapshotId"], ACTOR)
    assert projects.get(before["id"])["blocks"][0]["enabled"] is False
    assert service.history(before["id"])["total"] == 4


def test_history_pagination_and_preview_are_read_only_and_exclude_operational_records(site):
    repo, projects, service, original = site
    before = projects.get(original["sourceId"])
    history = service.history(before["id"], limit=1, skip=1)
    assert history["total"] == 2 and history["items"][0]["id"] == original["id"]
    preview = service.preview(before["id"], original["id"])
    assert preview["snapshot"]["blocks"][0]["enabled"] is True
    for key in ("ownerEmail", "ownerId", "payment", "customerData", "formSubmissions", "leadForms"):
        assert key not in preview["snapshot"]
    assert projects.get(before["id"]) == before
    assert "snapshot" not in history["items"][0]
    assert service.list_websites("client@example.test")["total"] == 1
    assert service.list_websites("nonexistent")["total"] == 0


def test_rejects_snapshot_from_another_website_and_stale_preview(site):
    repo, projects, service, original = site
    current = projects.get(original["sourceId"])
    other = deepcopy(original)
    other.update(id="other-snapshot", sourceId="cweb_other")
    repo.insert_document("customer_website_snapshots", other, "duplicate")
    for snapshot_id, expected, code in [
        ("other-snapshot", current["publishedSnapshotId"], "WEBSITE_VERSION_NOT_FOUND"),
        (original["id"], original["id"], "WEBSITE_VERSION_CONFLICT"),
        (current["publishedSnapshotId"], current["publishedSnapshotId"], "WEBSITE_VERSION_ALREADY_CURRENT"),
    ]:
        with pytest.raises(NuvlyError) as error:
            service.restore(current["id"], snapshot_id, expected, ACTOR)
        assert error.value.code == code
    assert projects.get(current["id"]) == current


def test_concurrent_customer_save_wins_and_failed_restore_snapshot_is_removed(site, monkeypatch):
    repo, projects, service, original = site
    current = projects.get(original["sourceId"])
    commit = repo.restore_customer_website

    def concurrent(project_id, expected, changes, event, **kwargs):
        projects.update(project_id, CustomerWebsiteUpdate(title="Cambio nuevo del cliente", saveAsDraft=True))
        return commit(project_id, expected, changes, event, **kwargs)

    monkeypatch.setattr(repo, "restore_customer_website", concurrent)
    with pytest.raises(NuvlyError) as error:
        service.restore(current["id"], original["id"], current["publishedSnapshotId"], ACTOR)
    assert error.value.code == "WEBSITE_VERSION_CONFLICT"
    assert projects.get(current["id"])["title"] == "Cambio nuevo del cliente"
    assert not any(row.get("restoration") for row in service.history(current["id"])["items"])
    # Removing an abandoned restore can leave a version gap; the next save must
    # use the maximum version, rather than reusing an existing number.
    projects.update(current["id"], CustomerWebsiteUpdate(title="Otro cambio", saveAsDraft=True))
    versions = [row["version"] for row in service.history(current["id"])["items"]]
    assert len(versions) == len(set(versions))


def test_concurrent_form_submission_is_preserved(site, monkeypatch):
    repo, projects, service, original = site
    current = projects.get(original["sourceId"])
    commit = repo.restore_customer_website

    def received_lead(project_id, expected, changes, event, **kwargs):
        repo.update_document_fields(
            "customer_websites", project_id, {"formSubmissions": [{"id": "new-lead"}]}, "missing", "missing"
        )
        return commit(project_id, expected, changes, event, **kwargs)

    monkeypatch.setattr(repo, "restore_customer_website", received_lead)
    service.restore(current["id"], original["id"], current["publishedSnapshotId"], ACTOR)
    assert projects.get(current["id"])["formSubmissions"] == [{"id": "new-lead"}]


def test_snapshot_storage_failure_keeps_editor_and_publication_untouched(site, monkeypatch):
    repo, projects, service, original = site
    current = projects.get(original["sourceId"])
    monkeypatch.setattr(
        repo, "insert_document", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("Storage failed"))
    )
    with pytest.raises(RuntimeError):
        service.restore(current["id"], original["id"], current["publishedSnapshotId"], ACTOR)
    assert projects.get(current["id"]) == current


@pytest.mark.parametrize("status", ["draft", "paid", "pending_payment"])
def test_unpublished_websites_cannot_be_restored(site, status):
    repo, projects, service, original = site
    current = projects.get(original["sourceId"])
    repo.update_document_fields("customer_websites", current["id"], {"customerStatus": status}, "missing", "missing")
    assert not service.history(current["id"])["canRestore"]
    with pytest.raises(NuvlyError) as error:
        service.restore(current["id"], original["id"], current["publishedSnapshotId"], ACTOR)
    assert error.value.code == "WEBSITE_NOT_PUBLISHED"


def test_admin_routes_validate_input_and_reject_customers_and_developers(site, monkeypatch):
    repo, projects, service, original = site
    monkeypatch.setattr(studio_routes, "website_versions", service)
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(studio_routes.admin_router, prefix="/api")
    client = ApiClient(app)
    path = "/api/admin/studio/customer-websites"
    assert client.get(path).status_code == 401
    principal = {"id": "customer", "accountType": "customer", "internalRole": None}

    def internal(_authorization=None, request=None):
        if principal["accountType"] != "internal":
            raise NuvlyError("Acceso interno requerido", 403, "INTERNAL_REQUIRED")
        return principal

    app.dependency_overrides[dependencies.get_current_internal_user] = internal
    monkeypatch.setattr(dependencies, "get_current_internal_user", internal)
    urls = [path, f"{path}/{original['sourceId']}/versions", f"{path}/{original['sourceId']}/versions/{original['id']}"]
    restore_url = urls[-1] + "/restore"
    for role, account in [(None, "customer"), ("developer", "internal")]:
        principal.update(internalRole=role, accountType=account)
        for url in urls:
            assert client.get(url).status_code == 403
        assert client.post(restore_url, json={"expectedSnapshotId": "x"}).status_code == 403
    principal.update(id=ACTOR["id"], name=ACTOR["name"], internalRole="admin", accountType="internal")
    for url in urls:
        assert client.get(url).status_code == 200
    assert client.get(path + "?limit=0").status_code == 422
    assert client.post(restore_url, json={}).status_code == 422
    current = projects.get(original["sourceId"])
    result = client.post(restore_url, json={"expectedSnapshotId": current["publishedSnapshotId"], "note": "Soporte"})
    assert result.status_code == 200 and result.json()["version"] == 3


def test_repository_uses_atomic_conditions_and_does_not_replace_operational_fields():
    class Collection:
        def find_one_and_update(self, filters, update, **kwargs):
            self.filters = filters
            self.update = update
            return {"id": "cweb_test"}

    collection = Collection()
    repo = DomainRepository()
    repo.collection = lambda _: collection
    changes = {"title": "Stable", "publishedSnapshotId": "new"}
    event = {"reason": "admin_version_restored"}
    repo.restore_customer_website("cweb_test", "expected", changes, event)
    assert collection.filters == {
        "id": "cweb_test",
        "publishedSnapshotId": "expected",
        "customerStatus": "published",
        "payment.status": "paid",
    }
    assert collection.update == {"$set": changes, "$push": {"statusHistory": event}}
