from __future__ import annotations

from typing import Any


class FakeCollection:
    def __init__(self, documents: list[dict[str, Any]]) -> None:
        self.documents = documents

    def count_documents(self, filters: dict[str, Any]) -> int:
        return len([document for document in self.documents if _matches(document, filters)])

    def find(self, filters: dict[str, Any], projection: dict[str, int] | None = None):
        documents = [document.copy() for document in self.documents if _matches(document, filters)]
        if projection:
            projected: list[dict[str, Any]] = []
            for document in documents:
                current = {}
                for key, enabled in projection.items():
                    if key == "_id" or not enabled:
                        continue
                    if key in document:
                        current[key] = document[key]
                projected.append(current)
            documents = projected
        return FakeCursor(documents)


class FakeCursor:
    def __init__(self, documents: list[dict[str, Any]]) -> None:
        self.documents = documents

    def limit(self, count: int):
        if count > 0:
            self.documents = self.documents[:count]
        return self

    def __iter__(self):
        return iter(self.documents)


class FakeDatabase:
    def __init__(self, collections: dict[str, list[dict[str, Any]]]) -> None:
        self.collections = {name: FakeCollection(documents) for name, documents in collections.items()}

    def __getitem__(self, collection_name: str) -> FakeCollection:
        return self.collections[collection_name]

    def list_collection_names(self) -> list[str]:
        return list(self.collections.keys())


def _matches(document: dict[str, Any], filters: dict[str, Any]) -> bool:
    for key, expected in filters.items():
        if document.get(key) != expected:
            return False
    return True


def test_studio_dashboard_returns_recent_activity_and_quick_summary(monkeypatch) -> None:
    from app.modules.domain import studio_routes

    fake_db = FakeDatabase(
        {
            "website_templates": [
                {"id": "wtpl_1", "title": "Template Web", "createdAt": "2026-05-25T10:00:00+00:00", "lastPublishedAt": "2026-05-25T12:00:00+00:00"},
            ],
            "invitation_templates": [
                {"id": "itpl_1", "title": "Template Invitación", "createdAt": "2026-05-25T09:00:00+00:00"},
            ],
            "customer_websites": [
                {"id": "cweb_1", "title": "Proyecto Web", "createdAt": "2026-05-25T11:00:00+00:00", "payment": {"paidAt": "2026-05-25T13:00:00+00:00"}},
            ],
            "pricing_components": [
                {"id": "comp_1", "name": "Hero Dinámico", "productType": "website", "updatedAt": "2026-05-25T08:00:00+00:00"},
                {"id": "comp_2", "name": "RSVP", "productType": "invitation", "updatedAt": "2026-05-25T07:00:00+00:00"},
            ],
            "pricing_extras": [
                {"id": "ext_1", "active": True},
                {"id": "ext_2", "active": False},
            ],
            "users": [
                {"id": "usr_1", "name": "Lara", "createdAt": "2026-05-25T06:00:00+00:00", "active": True},
                {"id": "usr_2", "name": "Mati", "createdAt": "2026-05-24T06:00:00+00:00", "active": False},
            ],
        }
    )

    monkeypatch.setattr(studio_routes, "get_database", lambda: fake_db)

    response = studio_routes.get_studio_dashboard()

    assert response["quickSummary"].webTemplates == 1
    assert response["quickSummary"].invitationTemplates == 1
    assert response["quickSummary"].webComponents == 1
    assert response["quickSummary"].invitationComponents == 1
    assert response["quickSummary"].extras == 1
    assert response["quickSummary"].activeUsers == 1
    assert len(response["recentActivity"]) >= 5
    assert response["recentActivity"][0]["title"] == 'Proyecto "Proyecto Web" pagado'
