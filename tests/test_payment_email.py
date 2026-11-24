import smtplib
from copy import deepcopy
from types import SimpleNamespace

import pytest
from test_payment_integration import owned_project as owned_project
from test_payment_integration import settings as settings
from test_payment_receipt_pdf import sample_payment

from app.core.errors import NuvlyError
from app.modules.payments import email_service, gateways
from app.modules.payments.email_service import build_payment_email
from app.modules.payments.integration_service import IntegrationPaymentService
from app.modules.payments.schemas import CreateCheckoutRequest, ManualPaymentConfirmationResponse
from app.modules.payments.terms import WEBSITE_TERMS


def payment_example():
    payment = sample_payment()
    accepted = payment["termsAcceptance"]
    payment.update(
        amount=accepted["amount"],
        currency="CLP",
        projectType="website",
        withCustomDomain=accepted["withCustomDomain"],
        customDomain=accepted["customDomain"],
    )
    return payment


def mail_settings():
    return SimpleNamespace(
        frontend_public_base_url="https://nuvly.example.test",
        support_contact_email="soporte@example.test",
        smtp_host="smtp.example.test",
        smtp_port=587,
        smtp_from_email="pagos@example.test",
        smtp_from_name="Nuvly",
        smtp_use_tls=True,
        smtp_username="user",
        smtp_password="test-password",
    )


def create_payment(owned_project, monkeypatch, sender):
    repository, project, user = owned_project
    monkeypatch.setattr(
        gateways,
        "create_test_checkout",
        lambda *a, **kw: {
            "gatewayUrl": "https://webpay3gint.transbank.cl/x",
            "gatewayToken": "token",
            "redirectMethod": "POST",
            "redirectFields": {"token_ws": "token"},
        },
    )
    service = IntegrationPaymentService(repository=repository, receipt_sender=sender)
    payment = service.create_integration_checkout(
        CreateCheckoutRequest(
            projectType="website",
            projectId=project["id"],
            provider="transbank",
            termsAccepted=True,
            termsVersion=WEBSITE_TERMS["version"],
        ),
        user,
    )
    return service, payment, user


def test_approval_sends_once_and_refreshes_do_not_duplicate(owned_project, monkeypatch):
    sent = []
    service, payment, user = create_payment(
        owned_project, monkeypatch, lambda payment: sent.append(deepcopy(payment)) or "sent"
    )
    monkeypatch.setattr(
        gateways, "verify_test_payment", lambda *a, **kw: {"status": "paid", "providerPaymentId": "token"}
    )
    result = service.read_integration_payment(payment["id"], "transbank", user)
    assert result["status"] == "paid"
    assert result["receiptEmail"]["status"] == "sent"
    assert result["receiptEmail"]["recipient"] == user["email"]
    assert sent[0]["paidAt"]
    assert sent[0]["ownerEmail"] == user["email"]
    url = result["finalUrl"]
    assert url
    assert sent[0]["websiteUrl"] == url
    project = service.assert_project_owner("website", payment["projectId"], user)
    from app.modules.domain.schemas import PaymentInfo

    assert PaymentInfo(**project["payment"]).finalUrl == url
    email = build_payment_email(sent[0], mail_settings())
    assert url in email.get_body(preferencelist=("plain",)).get_content()
    assert f'href="{url}"' in email.get_body(preferencelist=("html",)).get_content()
    service.read_integration_payment(payment["id"], "transbank", user)
    service.handle_return("transbank", payment["id"], {"token_ws": "token"})
    service.retry_receipt_email(payment["id"], "transbank", user)
    assert len(sent) == 1
    assert ManualPaymentConfirmationResponse(**result).receiptEmail["status"] == "sent"


@pytest.mark.parametrize("status", ["pending", "failed"])
def test_unapproved_payment_never_sends_confirmation(owned_project, monkeypatch, status):
    service, payment, user = create_payment(owned_project, monkeypatch, lambda payment: pytest.fail("Unapproved email"))
    monkeypatch.setattr(gateways, "verify_test_payment", lambda *a, **kw: {"status": status})
    response = service.read_integration_payment(payment["id"], "transbank", user)
    assert response["receiptEmail"] is None
    with pytest.raises(NuvlyError):
        service.retry_receipt_email(payment["id"], "transbank", user)


def test_mail_failure_does_not_change_payment_and_can_retry(owned_project, monkeypatch):
    def fail(payment):
        raise smtplib.SMTPException("test transport failure")

    service, payment, user = create_payment(owned_project, monkeypatch, fail)
    monkeypatch.setattr(
        gateways, "verify_test_payment", lambda *a, **kw: {"status": "paid", "providerPaymentId": "token"}
    )
    response = service.read_integration_payment(payment["id"], "transbank", user)
    assert response["status"] == "paid"
    assert response["receiptEmail"]["status"] == "failed"
    assert response["receiptEmail"]["sentAt"] is None
    sent = []
    service.receipt_email.sender = lambda payment: sent.append(payment) or "sent"
    with pytest.raises(NuvlyError):
        service.retry_receipt_email(payment["id"], "transbank", {"id": "other", "email": "other@example.test"})
    # Failed requests are throttled until the one-minute retry window.
    service.retry_receipt_email(payment["id"], "transbank", user)
    assert not sent
    service.repository.update_document_fields(
        "payment_receipt_emails", payment["id"], {"nextAttemptAt": "2000-01-01T00:00:00+00:00"}, "missing", "missing"
    )
    assert service.retry_receipt_email(payment["id"], "transbank", user)["receiptEmail"]["status"] == "sent"
    assert len(sent) == 1


def test_email_contains_exact_accepted_pdf_and_test_disclosure():
    payment = payment_example()
    payment.update(
        status="paid",
        environment="integration",
        testMode=True,
        ownerEmail="authenticated@example.test",
        provider="transbank",
        projectId="cweb_test",
        paidAt="2026-11-13T15:30:00+00:00",
    )
    message = build_payment_email(payment, mail_settings())
    assert message["To"] == "authenticated@example.test"
    assert str(message["Subject"]).startswith("[PRUEBA]")
    plain = message.get_body(preferencelist=("plain",)).get_content()
    assert "no se realizó un cobro real" in plain
    assert "flujo de pago y publicación del ambiente de pruebas" in plain
    assert "https://nuvly.example.test/customer/websites/cweb_test/edit" in plain
    assert "$114.900 CLP" in plain
    attachments = list(message.iter_attachments())
    assert len(attachments) == 1
    assert attachments[0].get_content_type() == "application/pdf"
    assert attachments[0].get_payload(decode=True).startswith(b"%PDF-")
    assert "&lt;Buildframe&gt;" in message.get_body(preferencelist=("html",)).get_content()


def test_real_domain_payment_includes_configuration_and_manual_renewal_instructions():
    payment = payment_example()
    payment.update(
        status="paid",
        testMode=False,
        environment="production",
        withCustomDomain=True,
        customDomain=None,
        provider="transbank",
        projectId="cweb_test",
        billingTerms=payment["termsAcceptance"]["billingTerms"],
    )
    message = build_payment_email(payment, mail_settings())
    assert "[PRUEBA]" not in str(message["Subject"])
    plain = message.get_body(preferencelist=("plain",)).get_content()
    assert "Te contactaremos" in plain
    assert "Por definir con nuestro equipo" in plain
    assert "requiere un nuevo pago" in plain
    assert "No se autorizaron cobros recurrentes automáticos" in plain
    assert "URL de tu página:" not in plain


@pytest.mark.parametrize("project_type,url_field", [("website", "websiteUrl"), ("invitation", "invitationUrl")])
def test_published_payment_email_delivers_the_exact_public_url(project_type, url_field):
    payment = payment_example()
    url = "https://nuvly.example.test/cweb_test/mi-pagina"
    payment.update(
        status="paid",
        testMode=False,
        environment="production",
        withCustomDomain=False,
        projectId="cweb_test",
        projectType=project_type,
        **{url_field: url},
    )
    message = build_payment_email(payment, mail_settings())
    plain = message.get_body(preferencelist=("plain",)).get_content()
    assert f"URL de tu página: {url}" in plain
    assert "Tu página ya está publicada" in plain
    assert f'href="{url}"' in message.get_body(preferencelist=("html",)).get_content()


def test_missing_smtp_is_not_reported_as_sent(monkeypatch):
    config = mail_settings()
    config.smtp_host = None
    monkeypatch.setattr(email_service, "get_settings", lambda: config)
    assert email_service.send_payment_email(sample_payment()) == "unavailable"


def test_smtp_uses_tls_and_reports_success_only_after_acceptance(monkeypatch):
    calls = []

    class FakeSMTP:
        def __init__(self, *args, **kwargs):
            calls.append("connect")

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def starttls(self, **kwargs):
            calls.append("tls")

        def login(self, *args):
            calls.append("login")

        def send_message(self, message):
            calls.append(message)
            return {}

    monkeypatch.setattr(email_service, "get_settings", mail_settings)
    monkeypatch.setattr(email_service.smtplib, "SMTP", FakeSMTP)
    payment = payment_example()
    payment.update(projectId="cweb_test", ownerEmail="customer@example.test", status="paid")
    assert email_service.send_payment_email(payment) == "sent"
    assert calls[:3] == ["connect", "tls", "login"]
    assert calls[-1]["To"] == "customer@example.test"
