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
            include_keys = [key for key, enabled in projection.items() if key != "_id" and enabled]
            for document in documents:
                if not include_keys:
                    current = {key: value for key, value in document.items() if key != "_id"}
                else:
                    current = {}
                    for key in include_keys:
                        if key in document:
                            current[key] = document[key]
                projected.append(current)
            documents = projected
        return FakeCursor(documents)

    def insert_one(self, document: dict[str, Any]):
        self.documents.append(document.copy())
        return None


class FakeCursor:
    def __init__(self, documents: list[dict[str, Any]]) -> None:
        self.documents = documents

    def limit(self, count: int):
        if count > 0:
            self.documents = self.documents[:count]
        return self

    def sort(self, key: str, direction: int):
        self.documents = sorted(self.documents, key=lambda item: item.get(key) or "", reverse=direction < 0)
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


def test_admin_can_create_internal_user_from_studio(monkeypatch) -> None:
    from app.modules.domain import studio_routes
    from app.modules.auth.schemas import InternalUserCreateRequest

    fake_db = FakeDatabase({"users": []})
    monkeypatch.setattr(studio_routes, "get_database", lambda: fake_db)
    monkeypatch.setattr(
        studio_routes,
        "auth_service",
        type(
            "StubAuthService",
            (),
            {
                "create_internal_user": staticmethod(
                    lambda **kwargs: {
                        "id": "usr_dev",
                        "name": kwargs["name"],
                        "email": kwargs["email"],
                        "accountType": "internal",
                        "internalRole": kwargs["internal_role"],
                        "emailVerified": True,
                        "active": True,
                        "authProviders": ["nuvly"],
                        "createdAt": "2026-07-01T00:00:00+00:00",
                        "updatedAt": "2026-07-01T00:00:00+00:00",
                        "lastLoginAt": None,
                    }
                )
            },
        )(),
    )

    response = studio_routes.create_internal_user(
        InternalUserCreateRequest(
            email="dev@nuvly.dev",
            password="Devpass1#",
            name="Dev Uno",
            internalRole="developer",
        ),
        current_user={"id": "usr_admin", "internalRole": "admin", "accountType": "internal"},
    )

    assert response["internalRole"] == "developer"


def test_list_internal_users_from_studio_filters_only_internal(monkeypatch) -> None:
    from app.modules.domain import studio_routes

    fake_db = FakeDatabase(
        {
            "users": [
                {
                    "id": "usr_admin",
                    "name": "Admin",
                    "email": "admin@nuvly.dev",
                    "accountType": "internal",
                    "internalRole": "admin",
                    "emailVerified": True,
                    "active": True,
                    "authProviders": ["nuvly"],
                    "createdAt": "2026-07-01T00:00:00+00:00",
                    "updatedAt": "2026-07-01T00:00:00+00:00",
                    "lastLoginAt": None,
                },
                {
                    "id": "usr_dev",
                    "name": "Dev Uno",
                    "email": "dev@nuvly.dev",
                    "accountType": "internal",
                    "internalRole": "developer",
                    "emailVerified": True,
                    "active": True,
                    "authProviders": ["nuvly"],
                    "createdAt": "2026-07-02T00:00:00+00:00",
                    "updatedAt": "2026-07-02T00:00:00+00:00",
                    "lastLoginAt": None,
                },
                {
                    "id": "usr_customer",
                    "name": "Cliente",
                    "email": "cliente@test.dev",
                    "accountType": "customer",
                    "emailVerified": False,
                    "active": True,
                    "authProviders": ["nuvly"],
                    "createdAt": "2026-07-03T00:00:00+00:00",
                    "updatedAt": "2026-07-03T00:00:00+00:00",
                    "lastLoginAt": None,
                },
            ]
        }
    )
    monkeypatch.setattr(studio_routes, "get_database", lambda: fake_db)

    response = studio_routes.list_internal_users()

    assert len(response) == 2
    assert all(item["accountType"] == "internal" for item in response)


def test_admin_can_create_discount_code_from_studio(monkeypatch) -> None:
    from app.modules.domain import studio_routes
    from app.modules.discounts.schemas import AdminDiscountCodeCreateRequest

    monkeypatch.setattr(
        studio_routes,
        "discount_code_service",
        type(
            "StubDiscountCodeService",
            (),
            {
                "create_code": staticmethod(
                    lambda payload: {
                        "id": "dsc_1",
                        "code": payload.code,
                        "discountType": payload.discountType,
                        "value": payload.value,
                        "appliesTo": payload.appliesTo,
                        "active": payload.active,
                        "description": payload.description,
                        "expiresAt": payload.expiresAt,
                        "createdAt": "2026-07-01T00:00:00+00:00",
                        "updatedAt": "2026-07-01T00:00:00+00:00",
                    }
                )
            },
        )(),
    )

    response = studio_routes.create_discount_code(
        AdminDiscountCodeCreateRequest(
            code="nuvly20",
            discountType="percentage",
            value=20,
            appliesTo="all",
            active=True,
            description="Campaña invierno",
        ),
        current_user={"id": "usr_admin", "internalRole": "admin", "accountType": "internal"},
    )

    assert response["code"] == "NUVLY20"
    assert response["discountType"] == "percentage"
    assert response["value"] == 20


def test_list_discount_codes_from_studio(monkeypatch) -> None:
    from app.modules.domain import studio_routes

    monkeypatch.setattr(
        studio_routes,
        "discount_code_service",
        type(
            "StubDiscountCodeService",
            (),
            {
                "list_codes": staticmethod(
                    lambda: [
                        {
                            "id": "dsc_2",
                            "code": "FIX5000",
                            "discountType": "fixed",
                            "value": 5000,
                            "appliesTo": "website",
                            "active": True,
                            "description": None,
                            "expiresAt": None,
                            "createdAt": "2026-07-02T00:00:00+00:00",
                            "updatedAt": "2026-07-02T00:00:00+00:00",
                        }
                    ]
                )
            },
        )(),
    )

    response = studio_routes.list_discount_codes()

    assert len(response) == 1
    assert response[0]["code"] == "FIX5000"
