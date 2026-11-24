from datetime import date, datetime, timedelta
from types import SimpleNamespace

import pytest
from pydantic import ValidationError
from test_payments_flow import InMemoryDomainRepository

from app.core.errors import NuvlyError
from app.modules.reporting.finance import FinanceService, OperatingCostInput, finance_report, month_period
from app.modules.reporting.service import CHILE


def payment(**changes):
    return {
        "id": "pay1",
        "environment": "production",
        "status": "paid",
        "amount": 10000,
        "currency": "CLP",
        "createdAt": "2026-11-01T12:00:00Z",
        "paidAt": "2026-11-02T12:00:00Z",
        **changes,
    }


def cost(**changes):
    return {
        "id": "cost1",
        "name": "Servidor",
        "category": "hosting",
        "environment": "production",
        "active": True,
        "amount": 2000,
        "kind": "actual",
        "incurredOn": "2026-11-01",
        **changes,
    }


def test_finances_separate_actual_costs_budgets_refunds_and_test_payments():
    payments = [
        payment(),
        payment(id="test", environment="integration", testMode=True),
        payment(
            id="refund",
            status="refunded",
            paidAt="2026-10-01T12:00:00Z",
            refundedAt="2026-11-04T12:00:00Z",
            amount=1000,
        ),
    ]
    costs = [
        cost(),
        cost(id="budget", kind="monthly_budget", incurredOn=None, startMonth="2026-10", amount=3000),
        cost(id="test", environment="test", amount=999999),
        cost(id="archived", active=False, amount=999999),
    ]
    report = finance_report(payments, costs, "2026-11", "production")
    assert report["summary"]["netRevenue"] == 9000
    assert report["summary"]["actualCosts"] == 2000
    assert report["summary"]["operatingResult"] == 7000
    assert report["summary"]["monthlyBudget"] == 3000
    assert report["summary"]["budgetScenarioResult"] == 6000
    assert len(report["costs"]) == 2 and len(report["history"]) == 6
    assert report["byCategory"] == [{"category": "hosting", "actual": 2000.0, "budget": 3000.0}]


def test_unregistered_costs_are_unknown_while_explicit_free_service_is_known():
    report = finance_report([payment()], [], "2026-11", "production")
    assert report["summary"]["operatingResult"] is None
    assert report["summary"]["budgetScenarioResult"] is None
    report = finance_report([payment()], [cost(amount=0)], "2026-11", "production")
    assert report["summary"]["operatingResult"] == 10000


def test_budget_start_end_and_archive_visibility_do_not_double_count():
    costs = [
        cost(kind="monthly_budget", startMonth="2026-09", endMonth="2026-10"),
        cost(id="old", incurredOn="2026-10-01"),
        cost(id="archived", active=False),
    ]
    report = finance_report([], costs, "2026-11", "production", include_archived=True)
    assert report["summary"]["actualCosts"] == 0
    assert report["summary"]["monthlyBudget"] == 0
    assert len(report["costs"]) == 1 and not report["costs"][0]["active"]
    assert report["history"][-2]["monthlyBudget"] == 2000
    assert report["history"][-2]["actualCosts"] == 2000


def test_operating_cost_input_validates_dates_amounts_and_required_fields():
    today = datetime.now(CHILE).date()
    base = {"name": "Hosting", "amount": 15000, "incurredOn": today}
    assert OperatingCostInput(**base).amount == 15000
    for changes in (
        {"amount": -1},
        {"amount": 1.2},
        {"incurredOn": today + timedelta(days=1)},
        {"incurredOn": None},
        {"name": "  "},
    ):
        with pytest.raises(ValidationError):
            OperatingCostInput(**{**base, **changes})
    with pytest.raises(NuvlyError):
        month_period("2026-13")
    with pytest.raises(ValueError):
        OperatingCostInput(
            name="Servidor", amount=2000, kind="monthly_budget", startMonth="2026-11", endMonth="2026-10"
        )


class Repo(InMemoryDomainRepository):
    def iter_operating_costs(self, mode):
        return [c for c in self.collections.get("operating_costs", []) if c["environment"] == mode]

    def iter_commercial_payments(self, *_):
        return iter([payment(environment="integration", testMode=True)])

    def system_overview_counts(self):
        return {"publishedWebsites": 1, "publishedInvitations": 0, "drafts": 2, "openSupport": 3, "waitingCustomer": 0}


def test_costs_persist_in_selected_environment_keep_audit_and_reject_moves(monkeypatch):
    monkeypatch.setattr(
        "app.modules.reporting.service.get_settings", lambda: SimpleNamespace(payments_environment="integration")
    )
    service = FinanceService(Repo())
    actor = {"id": "admin1"}
    payload = OperatingCostInput(name="Servidor", amount=2000, incurredOn=date(2026, 1, 1))
    saved = service.save(payload, actor)
    assert saved["environment"] == "test" and saved["createdBy"] == "admin1"
    edited = service.save(payload.model_copy(update={"amount": 3000}), actor, saved["id"])
    assert edited["history"][0]["previous"]["amount"] == 2000
    with pytest.raises(NuvlyError):
        service.save(payload.model_copy(update={"environment": "production"}), actor, saved["id"])
    with pytest.raises(NuvlyError):
        service.save(payload, actor, "missing")
