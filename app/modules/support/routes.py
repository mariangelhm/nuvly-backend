import csv
from io import StringIO
from typing import Literal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from app.modules.auth.dependencies import get_current_admin_user
from app.modules.reporting.service import ReportPeriod, csv_cell
from app.modules.support.schemas import (
    SupportContactRequest,
    SupportContactResponse,
    SupportReplyRequest,
    SupportTicketUpdate,
)
from app.modules.support.service import SupportService

router = APIRouter(prefix="/support", tags=["support"])
service = SupportService()
admin_router = APIRouter(
    prefix="/admin/support", tags=["admin-support"], dependencies=[Depends(get_current_admin_user)]
)


@router.post("/contact", response_model=SupportContactResponse)
def contact_support(payload: SupportContactRequest):
    return service.contact(payload)


@admin_router.get("/report")
def support_report(
    start: str | None = None,
    end: str | None = None,
    status: Literal["", "open", "in_progress", "waiting_customer", "resolved"] = "",
    category: Literal["", "question", "payment", "complaint", "domain", "technical", "other"] = "",
    search: str = Query("", max_length=200),
    page: int = Query(1, ge=1),
    pageSize: int = Query(25, ge=1, le=100),
):
    return service.report(ReportPeriod(start, end), status, category, search, page, pageSize)


@admin_router.get("/tickets.csv")
def support_csv(
    start: str | None = None,
    end: str | None = None,
    status: Literal["", "open", "in_progress", "waiting_customer", "resolved"] = "",
    category: Literal["", "question", "payment", "complaint", "domain", "technical", "other"] = "",
    search: str = Query("", max_length=200),
):
    period = ReportPeriod(start, end)

    def rows():
        buffer = StringIO()
        writer = csv.writer(buffer, delimiter=";")
        writer.writerow(
            [
                "Caso",
                "Nombre",
                "Correo",
                "Asunto",
                "Categoría",
                "Estado",
                "Prioridad",
                "Responsable",
                "Recibido UTC",
                "Resuelto UTC",
            ]
        )
        yield "\ufeff" + buffer.getvalue()
        for ticket in service.filtered_tickets(period, status, category, search):
            buffer.seek(0)
            buffer.truncate(0)
            writer.writerow(
                [
                    csv_cell(ticket.get(key))
                    for key in (
                        "reference",
                        "name",
                        "email",
                        "subject",
                        "category",
                        "status",
                        "priority",
                        "assigneeName",
                        "createdAt",
                        "resolvedAt",
                    )
                ]
            )
            yield buffer.getvalue()

    return StreamingResponse(
        rows(),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="nuvly-soporte-{period.start}-{period.end}.csv"',
            "Cache-Control": "private, no-store",
        },
    )


@admin_router.post("/tickets", status_code=201)
def create_ticket(payload: SupportContactRequest, user: dict = Depends(get_current_admin_user)):
    return service.contact(payload, source="admin", actor=user)


@admin_router.get("/tickets/{ticket_id}")
def get_ticket(ticket_id: str):
    return service.get(ticket_id)


@admin_router.patch("/tickets/{ticket_id}")
def update_ticket(ticket_id: str, payload: SupportTicketUpdate, user: dict = Depends(get_current_admin_user)):
    return service.update(ticket_id, payload, user)


@admin_router.post("/tickets/{ticket_id}/replies")
def reply_ticket(ticket_id: str, payload: SupportReplyRequest, user: dict = Depends(get_current_admin_user)):
    return service.reply(ticket_id, payload, user)
