"""Calendar comparisons based exclusively on confirmed payment events."""

from calendar import monthrange
from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal

from app.core.errors import NuvlyError
from app.modules.domain.repository import DomainRepository
from app.modules.reporting.service import (
    CHILE,
    ReportPeriod,
    money,
    parsed_time,
    resolve_report_environment,
    selected_payment,
)


def change(current, previous):
    return round((current - previous) / previous * 100, 1) if previous > 0 else None


def comparison_periods(year, compare_year, today=None):
    today = today or datetime.now(CHILE).date()
    if not (2000 <= year <= today.year and 2000 <= compare_year <= today.year) or year == compare_year:
        raise NuvlyError("Elige dos años distintos entre 2000 y el año actual.", 422, "INVALID_MARKETING_YEARS")
    partial = today.year in (year, compare_year)

    def period(value):
        end = (
            date(value, today.month, min(today.day, monthrange(value, today.month)[1]))
            if partial
            else date(value, 12, 31)
        )
        return ReportPeriod(f"{value}-01-01", end.isoformat())

    return period(year), period(compare_year), partial


def aggregate_year(records, period, environment, provider="", product_type="", templates=None, project_templates=None):
    templates, project_templates = templates or {}, project_templates or {}
    monthly = [{"month": m, "sales": Decimal(0), "refunds": Decimal(0), "count": 0, "days": 0} for m in range(1, 13)]
    weekdays = [{"weekday": d, "sales": Decimal(0), "count": 0, "days": 0} for d in range(7)]
    rankings = {
        key: defaultdict(lambda: {"sales": Decimal(0), "count": 0}) for key in ("products", "plans", "templates")
    }
    dates = defaultdict(lambda: {"sales": Decimal(0), "count": 0})
    invalid, estimated_dates = 0, 0
    for offset in range((period.end - period.start).days + 1):
        day = period.start + timedelta(days=offset)
        monthly[day.month - 1]["days"] += 1
        weekdays[day.weekday()]["days"] += 1
    for payment in records:
        event = selected_payment(payment, period, environment, provider, product_type)
        if not event:
            continue
        amount = money(payment.get("amount"))
        if amount is None:
            invalid += 1
            continue
        if event["refund"]:
            monthly[event["refunded"].astimezone(CHILE).month - 1]["refunds"] += event["refund"]
        if not event["approved"]:
            continue
        estimated_dates += parsed_time(payment.get("paidAt")) is None
        paid = event["paid"].astimezone(CHILE)
        for bucket in (monthly[paid.month - 1], weekdays[paid.weekday()], dates[paid.date().isoformat()]):
            bucket["sales"] += amount
            bucket["count"] += 1
        for group, key in (
            ("products", payment.get("projectType") or "unknown"),
            ("plans", f"{payment.get('projectType') or 'unknown'}:{payment.get('planTier') or 'unknown'}"),
            ("templates", payment.get("templateId") or project_templates.get(payment.get("projectId")) or "unknown"),
        ):
            rankings[group][key]["sales"] += amount
            rankings[group][key]["count"] += 1

    def serialize(bucket):
        return {key: float(value) if isinstance(value, Decimal) else value for key, value in bucket.items()}

    sales, refunds = sum(b["sales"] for b in monthly), sum(b["refunds"] for b in monthly)
    count = sum(b["count"] for b in monthly)
    return {
        "period": period.as_dict(),
        "summary": {
            "sales": float(sales),
            "refunds": float(refunds),
            "netSales": float(sales - refunds),
            "count": count,
            "averageSale": float(sales / count) if count else 0,
            "invalidAmounts": invalid,
            "estimatedApprovalDates": estimated_dates,
        },
        "monthly": [serialize(b | {"netSales": b["sales"] - b["refunds"]}) for b in monthly],
        "weekdays": [
            serialize(b | {"averagePerDay": b["sales"] / b["days"] if b["days"] else Decimal(0)}) for b in weekdays
        ],
        "rankings": {
            group: [
                {
                    "key": key,
                    "title": templates.get(key, "Sin identificar" if key == "unknown" else key),
                    **serialize(bucket),
                }
                for key, bucket in sorted(
                    values.items(), key=lambda pair: (pair[1]["sales"], pair[1]["count"]), reverse=True
                )
            ]
            for group, values in rankings.items()
        },
        "bestDates": [
            {"date": key, **serialize(value)}
            for key, value in sorted(dates.items(), key=lambda pair: (pair[1]["sales"], pair[1]["count"]), reverse=True)
        ][:10],
    }


def build_marketing_report(
    current_records,
    previous_records,
    current_period,
    previous_period,
    environment,
    provider="",
    product_type="",
    templates=None,
    project_templates=None,
    partial=False,
):
    current = aggregate_year(
        current_records, current_period, environment, provider, product_type, templates, project_templates
    )
    previous = aggregate_year(
        previous_records, previous_period, environment, provider, product_type, templates, project_templates
    )
    months = [
        {"month": a["month"], "current": a, "previous": b, "salesChangePercent": change(a["sales"], b["sales"])}
        for a, b in zip(current["monthly"], previous["monthly"])
    ]
    weekdays = [
        {"weekday": a["weekday"], "current": a, "previous": b}
        for a, b in zip(current["weekdays"], previous["weekdays"])
    ]
    best_month = max((m for m in current["monthly"] if m["count"]), key=lambda m: m["sales"], default=None)
    best_weekday = max((d for d in current["weekdays"] if d["count"]), key=lambda d: d["averagePerDay"], default=None)
    return {
        "environment": environment,
        "partialYear": partial,
        "current": current,
        "previous": previous,
        "months": months,
        "weekdays": weekdays,
        "changes": {
            key: change(current["summary"][key], previous["summary"][key])
            for key in ("sales", "netSales", "count", "averageSale")
        },
        "highlights": {
            "bestMonth": best_month["month"] if best_month else None,
            "bestWeekday": best_weekday["weekday"] if best_weekday else None,
        },
    }


class MarketingService:
    def __init__(self, repository=None):
        self.repository = repository or DomainRepository()

    def report(self, year, compare_year, environment="current", provider="", product_type=""):
        environment = resolve_report_environment(environment)
        current, previous, partial = comparison_periods(year, compare_year)
        templates = self.repository.reporting_templates()
        projects = {p["id"]: p.get("templateId") for p in self.repository.iter_reporting_project_templates()}
        return build_marketing_report(
            self.repository.iter_commercial_payments(current.since, current.until),
            self.repository.iter_commercial_payments(previous.since, previous.until),
            current,
            previous,
            environment,
            provider,
            product_type,
            templates,
            projects,
            partial,
        )
