from copy import deepcopy

import pytest
from test_payments_flow import InMemoryDomainRepository

import app.main as main_module
from app.modules.reporting.service import ReportPeriod, parsed_time
from app.modules.support.schemas import SupportContactRequest, SupportReplyRequest, SupportTicketUpdate
from app.modules.support.service import SupportService


class Repo(InMemoryDomainRepository):
    def iter_support_tickets(self, since, until):
        return iter(
            [
                deepcopy(t)
                for t in self.collections.get("support_tickets", [])
                if since <= parsed_time(t["createdAt"]) < until
            ]
        )

    def patch_support_ticket(self, ticket_id, updates, event=None, reply=None):
        ticket = self.find_document("support_tickets", {"id": ticket_id})
        ticket.update(updates)
        if event:
            ticket["events"].append(event)
        if reply:
            ticket["replies"].append(reply)
        return self.update_document_fields("support_tickets", ticket_id, ticket, "missing", "missing")

    def finish_support_reply(self, ticket_id, reply_id, status, now):
        ticket = self.find_document("support_tickets", {"id": ticket_id})
        for reply in ticket["replies"]:
            if reply["id"] == reply_id:
                reply["deliveryStatus"] = status
        if status == "sent":
            ticket["status"] = "waiting_customer"
            ticket.setdefault("firstReplyAt", now)
        return self.patch_support_ticket(ticket_id, ticket)


class Mail:
    def __init__(self, fail=False):
        self.fail, self.sent = fail, []

    def send_support_contact_email(self, **kwargs):
        if self.fail:
            raise OSError("SMTP down")
        self.sent.append(kwargs)

    def send_customer_reply(self, ticket, body):
        if self.fail:
            raise OSError("SMTP down")
        self.sent.append((ticket["email"], body))


def payload(**changes):
    return SupportContactRequest(
        **{
            "name": "Lara",
            "email": "lara@test.dev",
            "subject": "Necesito ayuda",
            "message": "Necesito ayuda con mi acceso al estudio.",
            **changes,
        }
    )


@pytest.mark.parametrize("fail", [False, True])
def test_contact_persists_even_when_mail_is_down(fail):
    repo, mail = Repo(), Mail(fail)
    service = SupportService(repository=repo, email_service=mail)
    result = service.contact(payload(category="complaint"))
    assert result["ok"] and result["notificationSent"] is not fail
    saved = service.get(result["ticketId"])
    assert saved["category"] == "complaint" and saved["status"] == "open"
    assert saved["notificationStatus"] == ("failed" if fail else "sent")
    if not fail:
        assert result["reference"] in mail.sent[0]["subject"]


def test_assignment_notes_reply_and_resolution(monkeypatch):
    monkeypatch.setattr("app.modules.support.service.utc_now_iso", lambda: "2026-11-10T12:00:00+00:00")
    repo, mail = Repo(), Mail()
    service = SupportService(repository=repo, email_service=mail)
    actor = {"id": "admin", "name": "Admin"}
    case = service.contact(payload(), source="admin", actor=actor)["ticketId"]
    updated = service.update(case, SupportTicketUpdate(assignToMe=True, priority="high", status="in_progress"), actor)
    assert updated["assigneeId"] == "admin" and len(updated["events"]) == 2
    service.reply(case, SupportReplyRequest(body="Revisar el caso", internal=True), actor)
    assert len(mail.sent) == 1
    updated = service.reply(case, SupportReplyRequest(body="Hola, ya puedes ingresar."), actor)
    assert updated["status"] == "waiting_customer" and updated["firstReplyAt"]
    first = updated["firstReplyAt"]
    mail.fail = True
    updated = service.reply(case, SupportReplyRequest(body="Segundo correo"), actor)
    assert updated["replies"][-1]["deliveryStatus"] == "failed" and updated["firstReplyAt"] == first
    service.update(case, SupportTicketUpdate(status="resolved"), actor)
    report = service.report(ReportPeriod("2026-11-01", "2026-11-30"))
    assert report["summary"]["resolved"] == 1 and report["summary"]["averageResolutionHours"] == 0
    assert service.report(ReportPeriod("2026-11-01", "2026-11-30"), search="LARA")["total"] == 1
    assert service.report(ReportPeriod("2026-11-01", "2026-11-30"), category="complaint")["total"] == 0
    assert service.report(ReportPeriod("2026-11-01", "2026-11-30"), status="open")["total"] == 0


def test_support_contact_validates_email_format():
    with pytest.raises(ValueError):
        payload(email="correo-invalido")


def test_support_routes_registered():
    paths = main_module.app.openapi()["paths"]
    assert "/api/support/contact" in paths
    assert "/api/admin/support/report" in paths
    assert "/api/admin/reports/commercial.csv" in paths
