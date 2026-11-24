"""Commercial reporting from confirmed transactions, with Chilean date boundaries."""

import csv
from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation
from io import StringIO
from zoneinfo import ZoneInfo

from app.core.config import get_settings
from app.core.errors import NuvlyError
from app.modules.domain.repository import DomainRepository

CHILE = ZoneInfo("America/Santiago")


def resolve_report_environment(environment="current"):
    if environment != "current":
        return environment
    return "test" if get_settings().payments_environment in ("integration", "test", "sandbox") else "production"


def parsed_time(value):
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)
    except TypeError, ValueError:
        return None


class ReportPeriod:
    def __init__(self, start=None, end=None):
        today = datetime.now(CHILE).date()
        try:
            self.start = date.fromisoformat(start) if start else today.replace(day=1)
            self.end = date.fromisoformat(end) if end else today
        except ValueError, TypeError:
            raise NuvlyError("Usa fechas válidas con formato año-mes-día.", 422, "INVALID_REPORT_DATES")
        if self.end < self.start or (self.end - self.start).days >= 366:
            raise NuvlyError(
                "Elige un período de hasta 366 días y una fecha final posterior a la inicial.",
                422,
                "INVALID_REPORT_DATES",
            )
        self.since = datetime.combine(self.start, time.min, CHILE).astimezone(timezone.utc)
        self.until = datetime.combine(self.end + timedelta(days=1), time.min, CHILE).astimezone(timezone.utc)

    def includes(self, value):
        return value is not None and self.since <= value < self.until

    def as_dict(self):
        return {"start": self.start.isoformat(), "end": self.end.isoformat(), "timezone": "America/Santiago"}


def money(value):
    try:
        amount = Decimal(str(value))
        return amount if amount.is_finite() and amount >= 0 else None
    except InvalidOperation, ValueError, TypeError:
        return None


def payment_environment(payment):
    if payment.get("testMode") is True or payment.get("environment") in ("integration", "test", "sandbox"):
        return "test"
    if payment.get("environment") == "production":
        return "production"
    # Legacy/unclassified records are not assumed to be real sales.
    return "unknown"


def selected_payment(payment, period, environment, provider="", product_type=""):
    if payment_environment(payment) != environment or payment.get("currency", "CLP") != "CLP":
        return None
    if provider and payment.get("provider") != provider:
        return None
    if product_type and payment.get("projectType") != product_type:
        return None
    created = parsed_time(payment.get("createdAt"))
    paid = parsed_time(payment.get("paidAt") or payment.get("updatedAt") or payment.get("createdAt"))
    refunded = parsed_time(payment.get("refundedAt") or payment.get("updatedAt"))
    approved = payment.get("status") in ("paid", "refunded") and period.includes(paid)
    refund_amount = payment.get("refundedAmount", payment.get("refundAmount"))
    refund_amount = (
        money(refund_amount)
        if refund_amount is not None
        else (money(payment.get("amount")) if payment.get("status") == "refunded" else Decimal(0))
    )
    refunded_in_period = bool(refund_amount and period.includes(refunded))
    if not (period.includes(created) or approved or refunded_in_period):
        return None
    return {
        "created": created,
        "paid": paid,
        "refunded": refunded,
        "approved": approved,
        "refund": refund_amount if refunded_in_period else Decimal(0),
    }


def payment_row(payment, event):
    return {
        key: payment.get(key)
        for key in (
            "id",
            "projectId",
            "projectTitle",
            "projectType",
            "ownerEmail",
            "provider",
            "status",
            "amount",
            "currency",
            "createdAt",
            "paidAt",
            "planTier",
        )
    } | {
        "refundAmount": float(event["refund"]),
        "emailStatus": payment.get("receiptEmailStatus") or "not_requested",
    }


def build_commercial_report(
    records, period, environment="production", provider="", product_type="", page=1, page_size=25
):
    gross = refunds = Decimal(0)
    counts = Counter()
    days = defaultdict(lambda: {"sales": Decimal(0), "refunds": Decimal(0), "count": 0})
    products = defaultdict(lambda: {"amount": Decimal(0), "count": 0})
    providers = defaultdict(lambda: {"amount": Decimal(0), "count": 0})
    customers = set()
    rows = []
    total = 0
    for payment in records:
        event = selected_payment(payment, period, environment, provider, product_type)
        if not event:
            continue
        amount = money(payment.get("amount"))
        if amount is None:
            counts["invalidAmounts"] += 1
            continue
        total += 1
        if (page - 1) * page_size < total <= page * page_size:
            rows.append(payment_row(payment, event))
        if period.includes(event["created"]):
            counts["attempts"] += 1
            counts[payment.get("status", "unknown")] += 1
        if event["approved"]:
            counts["approved"] += 1
            gross += amount
            day = days[event["paid"].astimezone(CHILE).date().isoformat()]
            day["sales"] += amount
            day["count"] += 1
            for group, key in (
                (products, payment.get("projectType") or "other"),
                (providers, payment.get("provider") or "other"),
            ):
                group[key]["amount"] += amount
                group[key]["count"] += 1
            customer = payment.get("ownerId") or payment.get("ownerEmail")
            if customer:
                customers.add(customer)
        if event["refund"]:
            refunds += event["refund"]
            counts["refunds"] += 1
            days[event["refunded"].astimezone(CHILE).date().isoformat()]["refunds"] += event["refund"]
    daily = []
    for offset in range((period.end - period.start).days + 1):
        day = (period.start + timedelta(days=offset)).isoformat()
        values = days[day]
        daily.append(
            {
                "date": day,
                "sales": float(values["sales"]),
                "refunds": float(values["refunds"]),
                "count": values["count"],
            }
        )

    def groups(values):
        return [
            {"key": key, "amount": float(value["amount"]), "count": value["count"]}
            for key, value in sorted(values.items(), key=lambda item: item[1]["amount"], reverse=True)
        ]

    return {
        "period": period.as_dict(),
        "environment": environment,
        "currency": "CLP",
        "summary": {
            "grossSales": float(gross),
            "refunds": float(refunds),
            "netSales": float(gross - refunds),
            "approvedPayments": counts["approved"],
            "customers": len(customers),
            "averageSale": float(gross / counts["approved"]) if counts["approved"] else 0,
            "attempts": counts["attempts"],
            "pendingPayments": counts["pending"],
            "failedPayments": counts["failed"],
            "invalidAmounts": counts["invalidAmounts"],
        },
        "daily": daily,
        "byProduct": groups(products),
        "byProvider": groups(providers),
        "payments": rows,
        "total": total,
        "page": page,
        "pageSize": page_size,
    }


def csv_cell(value):
    text = str(value if value is not None else "")
    return "'" + text if text.lstrip().startswith(("=", "+", "-", "@", "\t", "\r")) else text


class CommercialReportingService:
    def __init__(self, repository=None):
        self.repository = repository or DomainRepository()

    def report(self, period, environment="current", provider="", product_type="", page=1, page_size=25):
        environment = resolve_report_environment(environment)
        records = list(self.repository.iter_commercial_payments(period.since, period.until))
        report = build_commercial_report(records, period, environment, provider, product_type, page, page_size)
        approved = Counter()
        for payment in records:
            mode = payment_environment(payment)
            event = selected_payment(payment, period, mode, provider, product_type)
            if event and event["approved"] and money(payment.get("amount")) is not None:
                approved[mode] += 1
        report["approvedByEnvironment"] = {key: approved[key] for key in ("production", "test", "unknown")}
        return report

    def export(self, period, environment, provider="", product_type=""):
        environment = resolve_report_environment(environment)
        buffer = StringIO()
        writer = csv.writer(buffer, delimiter=";")
        writer.writerow(
            [
                "Referencia",
                "Proyecto",
                "Cliente",
                "Producto",
                "Plan",
                "Pasarela",
                "Estado",
                "Monto CLP",
                "Devolución CLP",
                "Fecha aprobación UTC",
                "Fecha creación UTC",
                "Correo",
                "Ambiente",
            ]
        )
        yield "\ufeff" + buffer.getvalue()
        for payment in self.repository.iter_commercial_payments(period.since, period.until):
            event = selected_payment(payment, period, environment, provider, product_type)
            if not event or money(payment.get("amount")) is None:
                continue
            buffer.seek(0)
            buffer.truncate(0)
            writer.writerow(
                [
                    csv_cell(payment.get(key))
                    for key in (
                        "id",
                        "projectTitle",
                        "ownerEmail",
                        "projectType",
                        "planTier",
                        "provider",
                        "status",
                        "amount",
                    )
                ]
                + [
                    float(event["refund"]),
                    csv_cell(payment.get("paidAt")),
                    csv_cell(payment.get("createdAt")),
                    csv_cell(payment.get("receiptEmailStatus")),
                    environment,
                ]
            )
            yield buffer.getvalue()
