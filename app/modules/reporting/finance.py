"""Cash-basis operating overview from confirmed payments and administrator-entered costs."""

from calendar import monthrange
from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.core.errors import NuvlyError
from app.core.utils import new_id, utc_now_iso
from app.modules.domain.repository import DomainRepository
from app.modules.reporting.service import (
    CHILE,
    ReportPeriod,
    build_commercial_report,
    money,
    resolve_report_environment,
    selected_payment,
)

CATEGORIES = Literal[
    "hosting", "database", "storage", "domain", "email", "payment_fees", "marketing", "software", "other"
]


def month_period(value=None):
    value = value or datetime.now(CHILE).strftime("%Y-%m")
    try:
        if len(value) != 7:
            raise ValueError()
        first = date.fromisoformat(value + "-01")
    except TypeError, ValueError:
        raise NuvlyError("Selecciona un mes válido.", 422, "INVALID_FINANCE_MONTH")
    return ReportPeriod(first.isoformat(), first.replace(day=monthrange(first.year, first.month)[1]).isoformat())


def shifted_month(value, offset):
    period = month_period(value)
    year, month = divmod(period.start.year * 12 + period.start.month - 1 + offset, 12)
    return f"{year:04d}-{month + 1:02d}"


class OperatingCostInput(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    category: CATEGORIES = "hosting"
    kind: Literal["actual", "monthly_budget"] = "actual"
    amount: int = Field(ge=0, le=1000000000000)
    incurredOn: date | None = None
    startMonth: str | None = None
    endMonth: str | None = None
    notes: str = Field(default="", max_length=1000)
    active: bool = True
    environment: Literal["current", "production", "test"] = "current"

    @field_validator("name", "notes", mode="before")
    @classmethod
    def trim_text(cls, value):
        return value.strip() if isinstance(value, str) else value

    @model_validator(mode="after")
    def validate_period(self):
        if self.kind == "actual":
            if self.incurredOn is None or self.incurredOn > datetime.now(CHILE).date():
                raise ValueError("Indica la fecha del gasto pagado, hasta hoy.")
            self.startMonth = self.endMonth = None
        else:
            if not self.startMonth:
                raise ValueError("Indica desde qué mes aplica el costo estimado.")
            month_period(self.startMonth)
            if self.endMonth:
                month_period(self.endMonth)
                if self.endMonth < self.startMonth:
                    raise ValueError("El mes final debe ser posterior al inicial.")
            self.incurredOn = None
        return self


def cost_in_month(cost, month):
    if cost.get("kind") == "actual":
        return str(cost.get("incurredOn") or "")[:7] == month
    return bool(
        cost.get("startMonth")
        and cost["startMonth"] <= month
        and (not cost.get("endMonth") or month <= cost["endMonth"])
    )


def finance_report(payments, costs, month, environment, include_archived=False):
    period = month_period(month)
    months = [shifted_month(month, offset) for offset in range(-5, 1)]
    payments, costs = list(payments), list(costs)
    costs = [c for c in costs if c.get("environment") == environment]
    history, groups = [], defaultdict(lambda: {"actual": Decimal(0), "budget": Decimal(0)})
    for value in months:
        window = month_period(value)
        revenue = refunds = Decimal(0)
        count = actual_count = budget_count = 0
        actual = budget = Decimal(0)
        for payment in payments:
            event = selected_payment(payment, window, environment)
            amount = money(payment.get("amount"))
            if not event or amount is None:
                continue
            if event["approved"]:
                revenue += amount
                count += 1
            refunds += event["refund"]
        for cost in costs:
            if not cost.get("active", True) or not cost_in_month(cost, value):
                continue
            amount = money(cost.get("amount"))
            if amount is None:
                continue
            if cost["kind"] == "actual":
                actual += amount
                actual_count += 1
            else:
                budget += amount
                budget_count += 1
            if value == month:
                groups[cost["category"]]["actual" if cost["kind"] == "actual" else "budget"] += amount
        net = revenue - refunds
        history.append(
            {
                "month": value,
                "grossRevenue": float(revenue),
                "refunds": float(refunds),
                "netRevenue": float(net),
                "approvedPayments": count,
                "actualCosts": float(actual),
                "monthlyBudget": float(budget),
                "operatingResult": float(net - actual) if actual_count else None,
                "budgetScenarioResult": float(net - budget) if budget_count else None,
                "actualCostCount": actual_count,
                "budgetCount": budget_count,
            }
        )
    visible = [c for c in costs if cost_in_month(c, month) and (include_archived or c.get("active", True))]
    visible.sort(
        key=lambda c: (c.get("incurredOn") or c.get("startMonth") or "", c.get("createdAt") or ""), reverse=True
    )
    return {
        "period": period.as_dict(),
        "environment": environment,
        "currency": "CLP",
        "summary": history[-1],
        "history": history,
        "byCategory": [
            {"category": key, "actual": float(value["actual"]), "budget": float(value["budget"])}
            for key, value in sorted(groups.items(), key=lambda item: item[1]["actual"], reverse=True)
        ],
        "costs": visible,
    }


class FinanceService:
    def __init__(self, repository=None):
        self.repository = repository or DomainRepository()

    def report(self, month=None, environment="current", include_archived=False):
        month = month or datetime.now(CHILE).strftime("%Y-%m")
        period = month_period(month)
        if not 2000 <= period.start.year <= 2100:
            raise NuvlyError("Selecciona un mes entre los años 2000 y 2100.", 422, "INVALID_FINANCE_MONTH")
        first = month_period(shifted_month(month, -5))
        mode = resolve_report_environment(environment)
        return finance_report(
            self.repository.iter_commercial_payments(first.since, period.until),
            self.repository.iter_operating_costs(mode),
            month,
            mode,
            include_archived,
        )

    def save(self, payload, actor, cost_id=None):
        mode, now = resolve_report_environment(payload.environment), utc_now_iso()
        current = self.repository.find_document("operating_costs", {"id": cost_id}) if cost_id else None
        if cost_id and not current:
            raise NuvlyError("No encontramos ese costo.", 404, "OPERATING_COST_NOT_FOUND")
        if current and current.get("environment") != mode:
            raise NuvlyError("Edita el costo desde su ambiente original.", 409, "OPERATING_COST_ENVIRONMENT_MISMATCH")
        values = {
            **payload.model_dump(mode="json"),
            "environment": mode,
            "currency": "CLP",
            "updatedAt": now,
            "updatedBy": actor["id"],
        }
        if current:
            values["history"] = [
                *current.get("history", []),
                {
                    "at": now,
                    "actorId": actor["id"],
                    "previous": {
                        key: current.get(key)
                        for key in (
                            "name",
                            "category",
                            "kind",
                            "amount",
                            "incurredOn",
                            "startMonth",
                            "endMonth",
                            "active",
                        )
                    },
                },
            ]
            return self.repository.update_document_fields(
                "operating_costs", cost_id, values, "No encontramos ese costo.", "OPERATING_COST_NOT_FOUND"
            )
        return self.repository.insert_document(
            "operating_costs",
            {"id": new_id("cost"), "createdAt": now, "createdBy": actor["id"], **values},
            "El costo ya existe.",
            "OPERATING_COST_EXISTS",
        )

    def overview(self):
        mode = resolve_report_environment()
        finances = self.report(environment=mode)
        period = month_period()
        payments = build_commercial_report(
            self.repository.iter_commercial_payments(period.since, period.until), period, mode
        )
        operations = self.repository.system_overview_counts()
        return {
            "environment": mode,
            "period": finances["period"],
            "finance": finances["summary"],
            "payments": payments["summary"],
            "operations": operations,
        }
