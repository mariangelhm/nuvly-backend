import pytest
from fastapi import FastAPI

from app.core.errors import NuvlyError
from app.modules.auth import dependencies
from app.modules.reporting.routes import router
from app.modules.reporting.service import CommercialReportingService, ReportPeriod, build_commercial_report, csv_cell
from app.modules.support.routes import admin_router


def payment(**changes):
    return (
        dict(
            id="p1",
            environment="production",
            testMode=False,
            status="paid",
            amount=1000,
            currency="CLP",
            projectType="website",
            provider="transbank",
            ownerEmail="a@example.com",
            createdAt="2026-11-01T03:00:00+00:00",
            paidAt="2026-11-02T04:00:00+00:00",
            **changes,
        )
        if not changes
        else {**payment(), **changes}
    )


def test_sales_exclude_tests_unknown_pending_failed_and_bad_amounts():
    rows = [
        payment(),
        payment(id="test", environment="integration"),
        payment(id="unknown", environment=None),
        payment(id="pending", status="pending"),
        payment(id="failed", status="failed"),
        payment(id="invalid", amount="NaN"),
    ]
    report = build_commercial_report(rows, ReportPeriod("2026-11-01", "2026-11-30"))
    assert report["summary"]["grossSales"] == 1000
    assert report["summary"]["pendingPayments"] == 1
    assert report["summary"]["failedPayments"] == 1
    assert report["summary"]["invalidAmounts"] == 1
    assert report["total"] == 3
    tests = build_commercial_report(rows, ReportPeriod("2026-11-01", "2026-11-30"), "test")
    assert tests["summary"]["grossSales"] == 1000


def test_refund_of_previous_month_and_partial_refund_use_event_date():
    rows = [
        payment(
            status="refunded",
            createdAt="2026-10-01T12:00:00Z",
            paidAt="2026-10-01T12:00:00Z",
            refundedAt="2026-11-04T12:00:00Z",
        ),
        payment(id="partial", refundedAmount=200, refundedAt="2026-11-05T12:00:00Z"),
    ]
    result = build_commercial_report(rows, ReportPeriod("2026-11-01", "2026-11-30"))
    assert result["summary"]["grossSales"] == 1000
    assert result["summary"]["refunds"] == 1200
    assert result["summary"]["netSales"] == -200
    assert sum(day["refunds"] for day in result["daily"]) == 1200


def test_chile_boundaries_pagination_and_filters():
    period = ReportPeriod("2026-11-01", "2026-11-01")
    rows = [
        payment(id="before", paidAt="2026-11-01T02:59:59Z"),
        payment(id="first", paidAt="2026-11-01T03:00:00Z"),
        payment(id="last", paidAt="2026-11-02T02:59:59Z"),
        payment(id="after", paidAt="2026-11-02T03:00:00Z"),
        payment(id="invitation", projectType="invitation", paidAt="2026-11-01T12:00:00Z"),
    ]
    result = build_commercial_report(rows, period, product_type="website", page=2, page_size=1)
    assert result["summary"]["grossSales"] == 2000
    assert result["total"] == 4  # All four attempts were created in this date range.
    assert len(result["payments"]) == 1
    assert build_commercial_report(rows, period, provider="mercadopago")["total"] == 0
    assert ReportPeriod("2026-07-01", "2026-07-01").since.hour == 4
    with pytest.raises(NuvlyError):
        ReportPeriod("2026-11-02", "2026-11-01")
    with pytest.raises(NuvlyError):
        ReportPeriod("bad", "2026-11-01")


def test_export_has_all_filtered_rows_and_protects_formulas():
    class Repo:
        def iter_commercial_payments(self, *_):
            return iter(
                [
                    payment(projectTitle='=HYPERLINK("bad")'),
                    payment(id="test", environment="test"),
                    payment(id="bad", amount="NaN"),
                ]
            )

    content = "".join(CommercialReportingService(Repo()).export(ReportPeriod("2026-11-01", "2026-11-30"), "production"))
    assert content.startswith("\ufeff")
    assert "'=HYPERLINK" in content
    assert "\r\ntest;" not in content and "\r\nbad;" not in content
    assert csv_cell(" +SUM(1)") == "' +SUM(1)"


@pytest.mark.parametrize(
    "path",
    [
        "/api/admin/reports/commercial",
        "/api/admin/reports/commercial.csv",
        "/api/admin/reports/marketing",
        "/api/admin/reports/behavior",
        "/api/admin/reports/renewals",
        "/api/admin/reports/overview",
        "/api/admin/reports/finance",
        "/api/admin/reports/finance/costs",
        "/api/admin/reports/finance/costs/{cost_id}",
        "/api/admin/support/report",
        "/api/admin/support/tickets/x",
        "/api/admin/support/tickets.csv",
    ],
)
def test_reports_require_admin_on_server(monkeypatch, path):
    app = FastAPI()
    app.include_router(router, prefix="/api")
    app.include_router(admin_router, prefix="/api")
    monkeypatch.setattr(dependencies, "get_current_internal_user", lambda _: {"id": "dev", "internalRole": "developer"})
    route = next(
        r
        for r in [*router.routes, *admin_router.routes]
        if getattr(r, "path", "") == path.removeprefix("/api").replace("/x", "/{ticket_id}")
    )
    assert any(dep.call is dependencies.get_current_admin_user for dep in route.dependant.dependencies)
    with pytest.raises(NuvlyError) as exc:
        dependencies.get_current_admin_user("Bearer test")
    assert exc.value.status_code == 403
