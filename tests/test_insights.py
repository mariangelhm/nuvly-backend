from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.modules.reporting import analytics
from app.modules.reporting.insights import STAGES, add_months, behavior_report, renewal_report
from app.modules.reporting.service import ReportPeriod

PERIOD = ReportPeriod("2026-11-01", "2026-11-30")
NOW = datetime(2026, 11, 13, 12, tzinfo=timezone.utc)


def payment(**changes):
    return {
        "id": "pay1",
        "projectId": "web1",
        "environment": "production",
        "status": "pending",
        "amount": 99900,
        "currency": "CLP",
        "createdAt": "2026-11-01T12:00:00Z",
        "updatedAt": "2026-11-01T12:00:00Z",
        "billingTerms": {"initialMonths": 12, "renewalAmount": 9990, "renewalPeriod": "monthly"},
        **changes,
    }


def project(**changes):
    return {
        "id": "web1",
        "projectType": "website",
        "title": "Mi web",
        "templateId": "tpl1",
        "ownerEmail": "client@example.com",
        "updatedAt": "2026-11-01T12:00:00Z",
        "customerStatus": "draft",
        "payments": [payment()],
        **changes,
    }


def event(name, sid="session1", **changes):
    return {
        "event": name,
        "sessionId": sid,
        "receivedAt": "2026-11-01T12:00:00Z",
        "environment": "production",
        "page": "catalog",
        "templateId": "tpl1",
        **changes,
    }


def test_ordered_funnel_uniques_interest_and_direct_entry():
    events = [event(key) for key, _ in STAGES]
    events += [
        event("template_viewed"),
        event("template_selected"),
        event("checkout_viewed", "direct"),
        event("page_view", "test", environment="test"),
    ]
    result = behavior_report(events, [], [], {"tpl1": "Salvia"}, PERIOD, "production", NOW)
    assert result["summary"]["sessions"] == 2
    assert result["summary"]["checkoutSessions"] == 2
    assert all(s["sessions"] == 1 for s in result["funnel"])
    assert result["interest"][0] == {"templateId": "tpl1", "title": "Salvia", "views": 1, "selections": 1}
    out_of_order = behavior_report(
        [event("checkout_viewed"), event("page_view")], [], [], {}, PERIOD, "production", NOW
    )
    assert out_of_order["funnel"][-1]["sessions"] == 0


def test_abandonment_is_project_based_ignores_drafts_and_recovered_payments():
    abandoned = project()
    recovered = project(id="recovered", payments=[payment(), payment(status="paid", createdAt="2026-12-01T12:00:00Z")])
    recent = project(id="recent", updatedAt="2026-11-13T11:00:00Z")
    failed = project(id="failed", payments=[payment(status="failed")])
    draft = project(id="draft", payments=[])
    test = project(id="test", payments=[payment(environment="integration")])
    result = behavior_report([], [], [abandoned, recovered, recent, failed, draft, test], {}, PERIOD, "production", NOW)
    assert {p["projectId"] for p in result["abandoned"]} == {"web1", "failed"}
    assert result["summary"]["draftsWithoutCheckout"] == 1
    duplicate = project(payments=[payment(), payment(id="pay2", createdAt="2026-11-02T12:00:00Z")])
    assert behavior_report([], [], [duplicate], {}, PERIOD, "production", NOW)["abandonedTotal"] == 1


def test_bestsellers_use_confirmed_sales_and_template_identity():
    payments = [
        payment(status="paid", paidAt="2026-11-02T12:00:00Z"),
        payment(status="paid", paidAt="2026-11-02T12:00:00Z", environment="integration"),
        payment(status="failed"),
        payment(status="paid", paidAt="2026-11-02T12:00:00Z", amount="NaN"),
    ]
    result = behavior_report(
        [], payments, [project(title="Customer changed title")], {"tpl1": "Salvia"}, PERIOD, "production", NOW
    )
    assert result["bestSellers"] == [{"templateId": "tpl1", "title": "Salvia", "count": 1, "amount": 99900}]


def test_renewals_use_first_publication_and_contract_not_latest_edit():
    paid = payment(status="paid", paidAt="2025-11-01T12:00:00Z")
    p = project(
        payments=[paid],
        firstPublishedAt="2026-11-01T12:00:00Z",
        firstSnapshot=[{"publishedAt": "2025-11-20T12:00:00Z"}],
        updatedAt="2026-11-12T12:00:00Z",
    )
    result = renewal_report([p], PERIOD, "production", now=NOW)
    assert result["renewals"][0]["dueAt"].startswith("2026-11-20")
    assert result["renewals"][0]["source"] == "contract_estimate"
    assert result["summary"]["upcoming"] == 1
    p["subscription"] = {"nextRenewalAt": "2026-12-01T12:00:00Z"}
    assert not renewal_report([p], PERIOD, "production", now=NOW)["renewals"]
    p["subscription"]["nextRenewalAt"] = "2026-11-15T12:00:00Z"
    assert renewal_report([p], PERIOD, "production", now=NOW)["renewals"][0]["source"] == "recorded"


def test_unknown_dates_tests_invitations_and_overdue_are_distinct():
    paid = payment(status="paid")
    overdue = project(payments=[paid], firstPublishedAt="2024-10-01T12:00:00Z")
    unknown = project(id="unknown", payments=[paid])
    missing = project(
        id="missing", payments=[payment(status="paid", billingTerms={})], firstPublishedAt="2025-11-01T12:00:00Z"
    )
    test = project(payments=[payment(status="paid", environment="integration")])
    invitation = project(projectType="invitation", payments=[paid])
    result = renewal_report([overdue, unknown, missing, test, invitation], PERIOD, "production", now=NOW)
    assert result["summary"] == {"upcoming": 0, "overdueToReview": 1, "awaitingPublication": 1, "missingTerms": 1}
    assert result["renewals"][0]["status"] == "past_due_review"
    assert not renewal_report([overdue], PERIOD, "production", include_overdue=False, now=NOW)["renewals"]
    assert add_months(datetime(2024, 2, 29), 12).isoformat().startswith("2025-02-28")


def test_telemetry_schema_does_not_accept_urls_or_arbitrary_actions():
    base = dict(id="a" * 32, sessionId="b" * 32, sequence=1, event="page_view", page="home", consent=True)
    for changes in (
        {"page": "/checkout?email=secret"},
        {"event": "capture_screen"},
        {"consent": False},
        {"templateId": "https://private"},
    ):
        with pytest.raises(ValidationError):
            analytics.AnalyticsEvent(**{**base, **changes})


def test_telemetry_server_sets_environment_expiry_and_deduplicates(monkeypatch):
    class Collection:
        def __init__(self):
            self.docs = {}

        def count_documents(self, *args, **kwargs):
            return len(self.docs)

        def update_one(self, query, update, **kwargs):
            self.docs.setdefault(query["id"], update["$setOnInsert"])

    col = Collection()
    monkeypatch.setattr(analytics.repository, "collection", lambda _: col)
    monkeypatch.setattr(analytics, "get_settings", lambda: SimpleNamespace(app_env="development"))
    payload = analytics.AnalyticsEvent(
        id="a" * 32, sessionId="b" * 32, sequence=1, event="page_view", page="home", consent=True
    )
    analytics.record_event(payload)
    analytics.record_event(payload)
    assert len(col.docs) == 1
    saved = next(iter(col.docs.values()))
    assert saved["environment"] == "test" and isinstance(saved["expiresAt"], datetime)
    assert not {"ip", "email", "url", "userAgent", "ownerId"} & saved.keys()
