from datetime import datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from app.modules.auth.dependencies import get_current_admin_user
from app.modules.reporting.finance import FinanceService, OperatingCostInput
from app.modules.reporting.insights import InsightsService
from app.modules.reporting.marketing import MarketingService
from app.modules.reporting.service import CHILE, CommercialReportingService, ReportPeriod

router = APIRouter(prefix="/admin/reports", tags=["admin-reports"], dependencies=[Depends(get_current_admin_user)])
service = CommercialReportingService()
insights = InsightsService()
marketing_service = MarketingService()
finance_service = FinanceService()


@router.get("/overview")
def overview():
    return finance_service.overview()


@router.get("/finance")
def finance(
    month: str | None = None,
    environment: Literal["current", "production", "test"] = "current",
    includeArchived: bool = False,
):
    return finance_service.report(month, environment, includeArchived)


@router.post("/finance/costs", status_code=201)
def create_cost(payload: OperatingCostInput, user: dict = Depends(get_current_admin_user)):
    return finance_service.save(payload, user)


@router.put("/finance/costs/{cost_id}")
def update_cost(cost_id: str, payload: OperatingCostInput, user: dict = Depends(get_current_admin_user)):
    return finance_service.save(payload, user, cost_id)


@router.get("/marketing")
def marketing(
    year: int,
    compareYear: int,
    environment: Literal["current", "production", "test"] = "current",
    provider: Literal["", "transbank", "mercadopago"] = "",
    productType: Literal["", "website", "invitation"] = "",
):
    return marketing_service.report(year, compareYear, environment, provider, productType)


@router.get("/behavior")
def behavior(
    start: str | None = None, end: str | None = None, environment: Literal["current", "production", "test"] = "current"
):
    return insights.behavior(ReportPeriod(start, end), environment)


@router.get("/renewals")
def renewals(
    start: str | None = None,
    end: str | None = None,
    environment: Literal["current", "production", "test"] = "current",
    includeOverdue: bool = True,
):
    today = datetime.now(CHILE).date()
    return insights.renewals(
        ReportPeriod(start or today.isoformat(), end or (today + timedelta(days=90)).isoformat()),
        environment,
        includeOverdue,
    )


@router.get("/commercial")
def commercial_report(
    start: str | None = None,
    end: str | None = None,
    environment: Literal["current", "production", "test"] = "current",
    provider: Literal["", "transbank", "mercadopago"] = "",
    productType: Literal["", "website", "invitation"] = "",
    page: int = Query(1, ge=1),
    pageSize: int = Query(25, ge=1, le=100),
):
    return service.report(ReportPeriod(start, end), environment, provider, productType, page, pageSize)


@router.get("/commercial.csv")
def commercial_csv(
    start: str | None = None,
    end: str | None = None,
    environment: Literal["current", "production", "test"] = "current",
    provider: Literal["", "transbank", "mercadopago"] = "",
    productType: Literal["", "website", "invitation"] = "",
):
    period = ReportPeriod(start, end)
    return StreamingResponse(
        service.export(period, environment, provider, productType),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="nuvly-ventas-{environment}-{period.start}-{period.end}.csv"',
            "Cache-Control": "private, no-store",
        },
    )
