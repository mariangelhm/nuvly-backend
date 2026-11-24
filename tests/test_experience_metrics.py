from datetime import timedelta
from types import SimpleNamespace

import pytest
from pydantic import ValidationError
from test_website_versions import ApiClient

from app.main import app
from app.modules.auth.dependencies import get_current_admin_user
from app.modules.reporting import analytics


@pytest.mark.parametrize(
    "changes",
    [
        {"consent": False},
        {"url": "private"},
        {"email": "private"},
        {"message": "private"},
        {"page": "private"},
        {"durationMs": float("nan")},
        {"durationMs": 60001},
        {"durationMs": None},
        {"kind": "render_error", "durationMs": 10},
    ],
)
def test_metric_rejects_unconsented_private_and_invalid_fields(changes):
    with pytest.raises(ValidationError):
        analytics.ExperienceMetric.model_validate(
            {"kind": "route_load", "page": "catalog", "durationMs": 100, "consent": True, **changes}
        )


def test_metric_records_bounded_data_with_expiry_and_no_identifiers(monkeypatch):
    saved = []
    monkeypatch.setattr(
        analytics,
        "repository",
        SimpleNamespace(collection=lambda _: SimpleNamespace(insert_one=lambda doc: saved.append(doc))),
    )
    payload = analytics.ExperienceMetric(kind="render_error", page="editor", productType="invitation", consent=True)
    assert analytics.record_experience_metric(payload) == {"accepted": True}
    document = saved[0]
    assert document["expiresAt"] - document["receivedAt"] == timedelta(days=30)
    assert set(document) == {"kind", "page", "productType", "receivedAt", "expiresAt", "environment"}


def test_metric_summary_requires_admin_and_uses_aggregate_only(monkeypatch):
    calls = []

    def aggregate(pipeline, **options):
        calls.append((pipeline, options))
        return iter([{"_id": {"page": "catalog", "kind": "route_load"}, "count": 3, "averageMs": 100}])

    monkeypatch.setattr(
        analytics, "repository", SimpleNamespace(collection=lambda _: SimpleNamespace(aggregate=aggregate))
    )
    client = ApiClient(app)
    assert client.get("/api/analytics/experience").status_code == 401
    app.dependency_overrides[get_current_admin_user] = lambda: {"id": "admin", "internalRole": "admin"}
    try:
        response = client.get("/api/analytics/experience?days=7")
        assert response.status_code == 200
        assert response.json()["items"][0]["count"] == 3
        assert calls[0][0][-1] == {"$limit": 100}
        assert calls[0][1] == {"maxTimeMS": 5000}
        assert client.get("/api/analytics/experience?days=31").status_code == 422
    finally:
        app.dependency_overrides.pop(get_current_admin_user, None)
