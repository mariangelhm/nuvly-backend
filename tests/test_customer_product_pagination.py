from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.modules.domain import customer_routes
from app.modules.domain.product_listing import CARD_FIELDS, customer_product_page_pipeline
from app.modules.domain.repository import DomainRepository
from app.modules.domain.services import CUSTOMER_WEBSITE_CONFIG, CustomerProjectService


def card(project_id="p1", product="website"):
    return {
        "id": project_id,
        "title": project_id,
        "productType": product,
        "planTier": "plus",
        "templateCategory": "corporate" if product == "website" else "wedding",
        "customerStatus": "draft",
        "ownerId": "owner",
        "templateId": "template",
        "templateSnapshotId": "snapshot",
        "selectedAt": "2026-11-14T10:00:00Z",
        "createdAt": "2026-11-14T10:00:00Z",
        "updatedAt": "2026-11-14T10:00:00Z",
    }


class AggregateCollection:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def aggregate(self, pipeline, **options):
        self.calls.append((deepcopy(pipeline), options))
        return iter(deepcopy(self.response))

    def find(self, *_args, **_kwargs):
        raise AssertionError("Dashboard must not materialize editor documents")


def test_product_page_is_owner_scoped_bounded_and_projected(monkeypatch):
    collection = AggregateCollection([{"items": [card()], "count": [{"total": 20000}]}])
    repository = DomainRepository()
    monkeypatch.setattr(repository, "collection", lambda name: collection)
    result = repository.customer_product_page("customer_websites", "owner", 10, 100)
    assert result["total"] == 20000
    assert len(result["items"]) == 1
    pipeline, options = collection.calls[0]
    assert pipeline[0] == {"$match": {"ownerId": "owner"}}
    assert pipeline[1] == {"$sort": {"updatedAt": -1, "id": 1}}
    projection = pipeline[2]["$project"]
    assert all(projection[field] == 1 for field in CARD_FIELDS)
    assert not {"blocks", "pages", "content", "guests", "formSubmissions", "customerData"} & projection.keys()
    facet = pipeline[-1]["$facet"]
    assert facet["items"][1:3] == [{"$skip": 100}, {"$limit": 10}]
    assert facet["count"] == [{"$count": "total"}]
    assert options == {"allowDiskUse": True, "maxTimeMS": 10000}


def test_product_page_without_identity_does_not_touch_database(monkeypatch):
    repository = DomainRepository()
    monkeypatch.setattr(repository, "collection", lambda *_: pytest.fail("No identity must mean no read"))
    assert repository.customer_product_page("customer_websites", None, 10, 0) == {"items": [], "total": 0}


@pytest.mark.parametrize("limit,skip", [(0, 0), (201, 0), (10, -1)])
def test_invalid_pagination_is_rejected(limit, skip):
    with pytest.raises(ValueError):
        customer_product_page_pipeline("owner", limit, skip)


def test_database_pipeline_preserves_unknown_age_and_distinguishes_paid_projects():
    pipeline = customer_product_page_pipeline("owner", 10, 0, now=datetime(2026, 11, 14, tzinfo=timezone.utc))
    assert pipeline[4]["$set"]["_touched"]["$convert"]["onError"] is None
    assert {"$eq": ["$_touched", None]} in pipeline[5]["$match"]["$expr"]["$or"]
    group_key = pipeline[6]["$group"]["_id"]["$cond"]
    assert group_key[1] == {"kind": "temporary", "template": "$templateId"}
    assert group_key[2] == {"kind": "project", "id": "$id"}


def test_dashboard_keeps_per_product_pages_and_totals_without_full_reads(monkeypatch):
    calls = []

    def page(kind):
        def load(**kwargs):
            calls.append(kwargs)
            return {
                "items": [card("same-time-b" if kind == "website" else "same-time-a", kind)],
                "total": 400 if kind == "website" else 300,
            }

        return load

    monkeypatch.setattr(customer_routes.invitation_service, "product_page_by_owner", page("invitation"))
    monkeypatch.setattr(customer_routes.website_service, "product_page_by_owner", page("website"))
    for service in (customer_routes.invitation_service, customer_routes.website_service):
        monkeypatch.setattr(service, "list_by_owner", lambda **_: pytest.fail("Unbounded legacy read"))
    result = customer_routes.list_customer_products(
        SimpleNamespace(base_url="https://example.test/"), {"id": "owner"}, 10, 20
    )
    assert (result.totalInvitations, result.totalWebsites) == (300, 400)
    assert [item.id for item in result.products] == ["same-time-a", "same-time-b"]
    assert len(result.invitations) == len(result.websites) == 1
    assert all(call["owner_id"] == "owner" and call["limit"] == 10 and call["skip"] == 20 for call in calls)
    assert "blocks" not in result.model_dump()["websites"][0]


def test_summary_service_does_not_require_editor_content():
    repository = SimpleNamespace(customer_product_page=lambda *_: {"items": [card()], "total": 900})
    service = CustomerProjectService(CUSTOMER_WEBSITE_CONFIG, repository=repository)
    result = service.product_page_by_owner("owner", limit=10, skip=20)
    assert result["total"] == 900
    assert result["items"][0]["id"] == "p1"
    assert "content" not in result["items"][0]
