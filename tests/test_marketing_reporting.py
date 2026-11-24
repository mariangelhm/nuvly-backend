from datetime import date

import pytest

from app.core.errors import NuvlyError
from app.modules.reporting.marketing import build_marketing_report, change, comparison_periods
from app.modules.reporting.service import CommercialReportingService, ReportPeriod


def payment(**changes):
    return {
        "id": "p1",
        "projectId": "web1",
        "projectType": "website",
        "templateId": "tpl1",
        "planTier": "basic",
        "provider": "transbank",
        "environment": "production",
        "status": "paid",
        "amount": 1000,
        "currency": "CLP",
        "createdAt": "2026-01-01T12:00:00Z",
        "paidAt": "2026-01-02T12:00:00Z",
        **changes,
    }


def test_equal_calendar_cutoff_and_leap_years():
    a, b, partial = comparison_periods(2026, 2025, date(2026, 11, 13))
    assert (a.end, b.end, partial) == (date(2026, 11, 13), date(2025, 11, 13), True)
    a, b, partial = comparison_periods(2024, 2023, date(2024, 2, 29))
    assert b.end == date(2023, 2, 28)
    a, b, partial = comparison_periods(2025, 2024, date(2026, 11, 13))
    assert a.end.month == b.end.month == 12 and not partial
    for year, other in ((2026, 2026), (2027, 2025), (1999, 2025)):
        with pytest.raises(NuvlyError):
            comparison_periods(year, other, date(2026, 11, 13))


def test_monthly_year_comparison_ranking_and_test_exclusion():
    a, b, partial = comparison_periods(2026, 2025, date(2026, 11, 13))
    current = [
        payment(),
        payment(id="p2", paidAt="2026-02-02T12:00:00Z", amount=3000),
        payment(id="test", environment="integration", amount=999999),
        payment(id="pending", status="pending"),
        payment(id="future", paidAt="2026-12-01T12:00:00Z"),
    ]
    previous = [payment(paidAt="2025-01-02T12:00:00Z", createdAt="2025-01-01T12:00:00Z", amount=2000)]
    result = build_marketing_report(
        current, previous, a, b, "production", templates={"tpl1": "Salvia"}, partial=partial
    )
    assert result["current"]["summary"]["sales"] == 4000
    assert result["changes"]["sales"] == 100
    assert result["months"][0]["salesChangePercent"] == -50
    assert result["months"][1]["salesChangePercent"] is None
    assert result["months"][11]["current"]["days"] == 0
    assert result["highlights"]["bestMonth"] == 2
    assert result["current"]["rankings"]["templates"][0]["title"] == "Salvia"
    assert result["current"]["rankings"]["plans"][0]["key"] == "website:basic"
    assert result["current"]["rankings"]["products"][0]["count"] == 2
    assert change(0, 100) == -100 and change(100, 0) is None and change(100, -10) is None


def test_weekday_averages_include_zero_sales_days_and_chile_midnight():
    a, b, _ = comparison_periods(2026, 2025, date(2026, 1, 31))
    # Friday 02:30 UTC is still Thursday in Chile.
    result = build_marketing_report([payment(paidAt="2026-01-02T02:30:00Z", amount=1000)], [], a, b, "production")
    thursday = result["weekdays"][3]["current"]
    friday = result["weekdays"][4]["current"]
    assert thursday["count"] == 1 and thursday["days"] == 5
    assert thursday["averagePerDay"] == 200
    assert friday["count"] == 0
    assert result["current"]["bestDates"][0]["date"] == "2026-01-01"


def test_refund_date_invalid_amount_filters_and_empty_periods():
    a, b, _ = comparison_periods(2026, 2025, date(2026, 11, 13))
    rows = [
        payment(status="refunded", paidAt="2025-01-01T12:00:00Z", refundedAt="2026-02-01T12:00:00Z"),
        payment(amount="NaN"),
        payment(projectType="invitation"),
    ]
    result = build_marketing_report(rows, [], a, b, "production", product_type="website")
    assert result["current"]["summary"]["sales"] == 0
    assert result["current"]["summary"]["refunds"] == 1000
    assert result["current"]["summary"]["netSales"] == -1000
    assert result["current"]["summary"]["invalidAmounts"] == 1
    assert result["highlights"]["bestMonth"] is None
    assert not result["current"]["rankings"]["templates"]


def test_commercial_explains_approved_payments_hidden_in_other_environments():
    class Repo:
        def iter_commercial_payments(self, *_):
            return iter(
                [
                    payment(environment="integration", testMode=True),
                    payment(id="failed", environment="integration", status="failed"),
                ]
            )

    report = CommercialReportingService(Repo()).report(ReportPeriod("2026-01-01", "2026-01-31"), "production")
    assert report["summary"]["grossSales"] == 0
    assert report["approvedByEnvironment"]["test"] == 1


def test_current_environment_counts_test_payments_by_default(monkeypatch):
    from types import SimpleNamespace

    monkeypatch.setattr(
        "app.modules.reporting.service.get_settings", lambda: SimpleNamespace(payments_environment="integration")
    )

    class Repo:
        def iter_commercial_payments(self, *_):
            return iter([payment(environment="integration", testMode=True)])

    report = CommercialReportingService(Repo()).report(ReportPeriod("2026-01-01", "2026-01-31"), "current")
    assert report["environment"] == "test"
    assert report["summary"]["grossSales"] == 1000
    assert report["summary"]["approvedPayments"] == 1
