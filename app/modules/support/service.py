from __future__ import annotations

import logging
from collections import Counter

from app.core.errors import NuvlyError
from app.core.utils import new_id, utc_now_iso
from app.modules.domain.repository import DomainRepository
from app.modules.reporting.service import parsed_time
from app.modules.support.email_service import SupportEmailService

logger = logging.getLogger(__name__)


class SupportService:
    def __init__(self, email_service=None, repository=None):
        self.email_service = email_service or SupportEmailService()
        self.repository = repository or DomainRepository()

    def contact(self, payload, source="contact_form", actor=None):
        now = utc_now_iso()
        ticket_id = new_id("case")
        ticket = {
            "id": ticket_id,
            "reference": "NV-" + ticket_id.removeprefix("case_").upper(),
            **payload.model_dump(),
            "source": source,
            "status": "open",
            "priority": "normal",
            "createdAt": now,
            "updatedAt": now,
            "replies": [],
            "events": [],
            "notificationStatus": "pending",
        }
        if actor:
            ticket["events"].append(
                {
                    "at": now,
                    "actorId": actor["id"],
                    "actorName": actor.get("name") or actor.get("email"),
                    "changes": {"source": "Registro manual"},
                }
            )
        self.repository.insert_document("support_tickets", ticket, "El caso ya existe.", "DUPLICATED_SUPPORT_TICKET")
        notified = False
        try:
            self.email_service.send_support_contact_email(
                name=payload.name,
                email=payload.email,
                subject=f"[{ticket['reference']}] {payload.subject}",
                message=payload.message,
            )
            notified = True
        except Exception:
            logger.warning("Support notification failed | ticketId=%s", ticket_id)
        self.repository.update_document_fields(
            "support_tickets",
            ticket_id,
            {"notificationStatus": "sent" if notified else "failed"},
            "Caso no encontrado.",
            "SUPPORT_TICKET_NOT_FOUND",
        )
        return {
            "ok": True,
            "message": f"Tu solicitud quedó registrada con el número {ticket['reference']}. Nuestro equipo la revisará.",
            "ticketId": ticket_id,
            "reference": ticket["reference"],
            "notificationSent": notified,
        }

    def get(self, ticket_id):
        ticket = self.repository.find_document("support_tickets", {"id": ticket_id})
        if not ticket:
            raise NuvlyError("No encontramos ese caso.", 404, "SUPPORT_TICKET_NOT_FOUND")
        return ticket

    def filtered_tickets(self, period, status="", category="", search=""):
        search = search.strip().casefold()
        for ticket in self.repository.iter_support_tickets(period.since, period.until):
            if status and ticket.get("status") != status or category and ticket.get("category") != category:
                continue
            if (
                search
                and search
                not in " ".join(
                    str(ticket.get(key) or "") for key in ("reference", "subject", "email", "name")
                ).casefold()
            ):
                continue
            yield ticket

    def report(self, period, status="", category="", search="", page=1, page_size=25):
        counts, categories = Counter(), Counter()
        resolution_hours, response_hours, rows = [], [], []
        total = 0
        for ticket in self.filtered_tickets(period, status, category, search):
            total += 1
            counts[ticket["status"]] += 1
            counts["notificationFailed"] += ticket.get("notificationStatus") == "failed"
            categories[ticket.get("category", "other")] += 1
            created, resolved, first_reply = (
                parsed_time(ticket.get(key)) for key in ("createdAt", "resolvedAt", "firstReplyAt")
            )
            if created and resolved and resolved >= created:
                resolution_hours.append((resolved - created).total_seconds() / 3600)
            if created and first_reply and first_reply >= created:
                response_hours.append((first_reply - created).total_seconds() / 3600)
            if (page - 1) * page_size < total <= page * page_size:
                rows.append(ticket)
        return {
            "period": period.as_dict(),
            "summary": {
                "received": total,
                "open": counts["open"],
                "inProgress": counts["in_progress"],
                "waitingCustomer": counts["waiting_customer"],
                "resolved": counts["resolved"],
                "notificationFailed": counts["notificationFailed"],
                "averageResolutionHours": round(sum(resolution_hours) / len(resolution_hours), 1)
                if resolution_hours
                else None,
                "averageFirstReplyHours": round(sum(response_hours) / len(response_hours), 1)
                if response_hours
                else None,
            },
            "byCategory": [{"key": key, "count": count} for key, count in categories.most_common()],
            "tickets": rows,
            "total": total,
            "page": page,
            "pageSize": page_size,
        }

    def update(self, ticket_id, payload, actor):
        ticket = self.get(ticket_id)
        updates = {key: value for key, value in payload.model_dump(exclude_none=True).items() if key != "assignToMe"}
        if payload.assignToMe:
            updates.update(assigneeId=actor["id"], assigneeName=actor.get("name") or actor.get("email"))
        now = utc_now_iso()
        if "status" in updates and updates["status"] != ticket["status"]:
            updates["resolvedAt"] = now if updates["status"] == "resolved" else None
        updates["updatedAt"] = now
        event = {
            "at": now,
            "actorId": actor["id"],
            "actorName": actor.get("name") or actor.get("email"),
            "changes": {key: value for key, value in updates.items() if key != "updatedAt"},
        }
        return self.repository.patch_support_ticket(ticket_id, updates, event=event)

    def reply(self, ticket_id, payload, actor):
        ticket = self.get(ticket_id)
        now = utc_now_iso()
        reply = {
            "id": new_id("reply"),
            "body": payload.body,
            "internal": payload.internal,
            "actorId": actor["id"],
            "actorName": actor.get("name") or actor.get("email"),
            "createdAt": now,
            "deliveryStatus": "internal" if payload.internal else "sending",
        }
        updated = self.repository.patch_support_ticket(ticket_id, {"updatedAt": now}, reply=reply)
        if payload.internal:
            return updated
        try:
            self.email_service.send_customer_reply(ticket, payload.body)
            delivery = "sent"
        except Exception:
            delivery = "failed"
            logger.warning("Support reply failed | ticketId=%s replyId=%s", ticket_id, reply["id"])
        return self.repository.finish_support_reply(ticket_id, reply["id"], delivery, utc_now_iso())
