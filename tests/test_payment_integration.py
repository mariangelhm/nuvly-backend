import hashlib
import hmac
import time
from copy import deepcopy
from types import SimpleNamespace

import pytest
from pydantic import SecretStr
from test_payments_flow import InMemoryDomainRepository, _create_customer_project

from app.core.errors import NuvlyError
from app.modules.domain.services import CUSTOMER_WEBSITE_CONFIG
from app.modules.payments import email_service as email_module
from app.modules.payments import gateways
from app.modules.payments import integration_service as module
from app.modules.payments.integration_service import IntegrationPaymentService
from app.modules.payments.schemas import CreateCheckoutRequest
from app.modules.payments.terms import WEBSITE_TERMS


@pytest.fixture
def settings(monkeypatch):
    value = SimpleNamespace(
        payments_environment="integration",
        app_env="test",
        mercadopago_test_access_token=None,
        mercadopago_test_webhook_secret=None,
        frontend_public_base_url="http://localhost:5173",
        public_base_url="http://localhost:8000",
        api_prefix="/api",
        smtp_host=None,
        smtp_from_email=None,
    )
    monkeypatch.setattr(gateways, "get_settings", lambda: value)
    monkeypatch.setattr(module, "get_settings", lambda: value)
    monkeypatch.setattr(email_module, "get_settings", lambda: value)
    return value


@pytest.fixture
def owned_project(settings):
    repository = InMemoryDomainRepository()
    project = _create_customer_project(repository)
    project.update(ownerId="customer-test", ownerEmail="customer@test.dev")
    repository.replace_document(
        CUSTOMER_WEBSITE_CONFIG.collection, project["id"], project, "missing", "missing", "duplicate"
    )
    return repository, project, {"id": "customer-test", "email": "customer@test.dev"}


def tbk_payment():
    return {
        "id": "pay_test",
        "projectId": "cweb_test",
        "provider": "transbank",
        "environment": "integration",
        "amount": 4990,
        "gatewayToken": "test-token",
        "gatewayOrder": "pay_test",
    }


def tbk_result(**patch):
    return {
        "buy_order": "pay_test",
        "session_id": "pay_test",
        "amount": 4990,
        "status": "AUTHORIZED",
        "response_code": 0,
        **patch,
    }


def test_webpay_uses_only_integration_host_and_public_test_credentials(settings, monkeypatch):
    calls = []
    monkeypatch.setattr(
        gateways,
        "_request",
        lambda *args, **kw: (
            calls.append((args, kw))
            or {"url": "https://webpay3gint.transbank.cl/webpayserver/initTransaction", "token": "test-token"}
        ),
    )
    result = gateways.create_test_checkout(
        "transbank", tbk_payment(), "http://localhost:8000/api/payments/return/transbank/pay_test"
    )
    assert result["redirectMethod"] == "POST"
    assert result["redirectFields"] == {"token_ws": "test-token"}
    args, _ = calls[0]
    assert args[1].startswith("https://webpay3gint.transbank.cl/")
    assert args[2]["Tbk-Api-Key-Id"] == "597055555532"
    assert args[3]["amount"] == 4990


@pytest.mark.parametrize("environment,app_env", [("production", "test"), ("integration", "production")])
def test_real_charges_are_blocked(settings, environment, app_env):
    settings.payments_environment = environment
    settings.app_env = app_env
    with pytest.raises(NuvlyError) as exc:
        gateways.create_test_checkout("transbank", tbk_payment(), "http://localhost/return")
    assert exc.value.code == "PAYMENTS_PRODUCTION_DISABLED"


def test_webpay_token_and_amount_must_match(settings, monkeypatch):
    with pytest.raises(NuvlyError):
        gateways.verify_test_payment(tbk_payment(), "attacker-token", commit=True)
    monkeypatch.setattr(gateways, "_request", lambda *a, **kw: tbk_result(amount=1))
    with pytest.raises(NuvlyError) as exc:
        gateways.verify_test_payment(tbk_payment(), "test-token", commit=True)
    assert exc.value.code == "PAYMENT_VERIFICATION_MISMATCH"


def test_webpay_pending_declined_and_authorized_are_distinct(settings, monkeypatch):
    for data, expected in [
        (tbk_result(), "paid"),
        (tbk_result(status="FAILED", response_code=-1), "failed"),
        (tbk_result(status="INITIALIZED", response_code=None), "pending"),
    ]:
        data = {k: v for k, v in data.items() if v is not None}
        monkeypatch.setattr(gateways, "_request", lambda *a, **kw: data)
        assert gateways.verify_test_payment(tbk_payment())["status"] == expected


def test_mp_requires_configuration_and_rejects_real_seller(settings, monkeypatch):
    with pytest.raises(NuvlyError) as exc:
        gateways._mp_headers()
    assert exc.value.code == "MERCADOPAGO_TEST_NOT_CONFIGURED"
    settings.mercadopago_test_access_token = SecretStr("APP_USR-example")
    monkeypatch.setattr(gateways, "_request", lambda *a, **kw: {"tags": [], "site_id": "MLC"})
    with pytest.raises(NuvlyError) as exc:
        gateways._mp_headers()
    assert exc.value.code == "MERCADOPAGO_TEST_ACCOUNT_REQUIRED"


def test_mp_uses_sandbox_checkout_and_fixed_server_amount(settings, monkeypatch):
    settings.mercadopago_test_access_token = SecretStr("TEST-example")
    calls = []
    monkeypatch.setattr(
        gateways,
        "_request",
        lambda *a, **kw: (
            calls.append(a)
            or {
                "id": "pref-test",
                "sandbox_init_point": "https://sandbox.mercadopago.cl/checkout/v1/redirect?pref_id=test",
            }
        ),
    )
    result = gateways.create_test_checkout(
        "mercadopago", tbk_payment(), "http://localhost:8000/api/payments/return/mercadopago/pay_test"
    )
    assert result["redirectMethod"] == "GET"
    assert calls[0][3]["external_reference"] == "pay_test"
    assert calls[0][3]["items"][0]["currency_id"] == "CLP"
    assert "auto_return" not in calls[0][3]  # local HTTP callback


@pytest.mark.parametrize(
    "patch",
    [{"live_mode": True}, {"external_reference": "other-order"}, {"transaction_amount": 1}, {"currency_id": "USD"}],
)
def test_mp_rejects_live_or_mismatched_payments(settings, monkeypatch, patch):
    settings.mercadopago_test_access_token = SecretStr("TEST-example")
    result = {
        "id": 123,
        "live_mode": False,
        "external_reference": "pay_test",
        "currency_id": "CLP",
        "transaction_amount": 4990,
        "status": "approved",
        **patch,
    }
    monkeypatch.setattr(gateways, "_request", lambda *a, **kw: result)
    payment = {**tbk_payment(), "provider": "mercadopago"}
    with pytest.raises(NuvlyError) as exc:
        gateways.verify_test_payment(payment, "123")
    assert exc.value.code == "PAYMENT_VERIFICATION_MISMATCH"


def test_public_provider_state_distinguishes_missing_credentials(settings):
    providers = IntegrationPaymentService(repository=InMemoryDomainRepository()).providers()["providers"]
    assert providers[0]["enabled"] is False
    assert providers[1]["enabled"] is True


def test_uat_only_provider_approval_completes_the_project_lifecycle(owned_project, monkeypatch):
    repo, project, user = owned_project
    service = IntegrationPaymentService(repository=repo)
    monkeypatch.setattr(
        gateways,
        "create_test_checkout",
        lambda *a, **kw: {
            "gatewayUrl": "https://webpay3gint.transbank.cl/webpayserver/initTransaction",
            "gatewayToken": "token",
            "gatewayOrder": "order",
            "redirectMethod": "POST",
            "redirectFields": {"token_ws": "token"},
        },
    )
    payment = service.create_integration_checkout(
        CreateCheckoutRequest(
            termsAccepted=True,
            termsVersion=WEBSITE_TERMS["version"],
            projectType="website",
            projectId=project["id"],
            provider="transbank",
        ),
        user,
    )
    assert payment["checkoutUrl"].startswith("http://localhost:5173/checkout/transbank/")
    monkeypatch.setattr(
        gateways, "verify_test_payment", lambda *a, **kw: {"status": "pending", "providerPaymentId": None}
    )
    assert service.read_integration_payment(payment["id"], "transbank", user)["ok"] is None
    pending = repo.find_document(CUSTOMER_WEBSITE_CONFIG.collection, {"id": project["id"]})
    assert pending["customerStatus"] == "pending_payment" and pending.get("publishedSnapshotId") is None
    monkeypatch.setattr(
        gateways, "verify_test_payment", lambda *a, **kw: {"status": "paid", "providerPaymentId": "token"}
    )
    response = service.read_integration_payment(payment["id"], "transbank", user)
    assert response["ok"] is True
    assert response["testMode"] is True
    assert response["finalUrl"].endswith(f"/{project['id']}/{project['publicSlug']}")
    stored = repo.find_document(CUSTOMER_WEBSITE_CONFIG.collection, {"id": project["id"]})
    assert stored["customerStatus"] == "published"
    assert stored["payment"]["testMode"] is True
    assert stored["payment"]["environment"] == "integration"
    assert stored.get("publishedSnapshotId")
    snapshot_id = stored["publishedSnapshotId"]
    monkeypatch.setattr(
        gateways, "verify_test_payment", lambda *a, **kw: pytest.fail("An approved payment must not be committed twice")
    )
    service.read_integration_payment(payment["id"], "transbank", user)
    assert (
        repo.find_document(CUSTOMER_WEBSITE_CONFIG.collection, {"id": project["id"]})["publishedSnapshotId"]
        == snapshot_id
    )


def test_another_customer_cannot_read_a_payment(owned_project, monkeypatch):
    repo, project, user = owned_project
    service = IntegrationPaymentService(repository=repo)
    monkeypatch.setattr(
        gateways,
        "create_test_checkout",
        lambda *a, **kw: {"gatewayUrl": "https://webpay3gint.transbank.cl/x", "gatewayToken": "token"},
    )
    payment = service.create_integration_checkout(
        CreateCheckoutRequest(
            termsAccepted=True,
            termsVersion=WEBSITE_TERMS["version"],
            projectType="website",
            projectId=project["id"],
            provider="transbank",
        ),
        user,
    )
    with pytest.raises(NuvlyError):
        service.read_integration_payment(payment["id"], "transbank", {"id": "other", "email": "other@test.dev"})


@pytest.mark.parametrize("test_mode", [False, True])
@pytest.mark.parametrize("status", ["paid", "published"])
def test_already_paid_project_cannot_create_another_gateway_checkout(owned_project, monkeypatch, test_mode, status):
    repo, project, user = owned_project
    project.update(
        customerStatus=status, payment={"status": "paid", "testMode": test_mode, "paymentId": "existing-payment"}
    )
    repo.replace_document(CUSTOMER_WEBSITE_CONFIG.collection, project["id"], project, "missing", "missing", "duplicate")
    monkeypatch.setattr(
        gateways,
        "create_test_checkout",
        lambda *a, **kw: pytest.fail("Paid projects must not create a gateway transaction"),
    )
    service = IntegrationPaymentService(repository=repo)
    payload = CreateCheckoutRequest(
        termsAccepted=True,
        termsVersion=WEBSITE_TERMS["version"],
        projectType="website",
        projectId=project["id"],
        provider="transbank",
    )
    with pytest.raises(NuvlyError) as error:
        service.create_integration_checkout(payload, user)
    assert error.value.code == "PROJECT_ALREADY_PAID"
    from app.modules.payments.service import PaymentService

    with pytest.raises(NuvlyError) as error:
        PaymentService(repository=repo).create_checkout(payload)
    assert error.value.code == "PROJECT_ALREADY_PAID"
    assert repo.find_document(CUSTOMER_WEBSITE_CONFIG.collection, {"id": project["id"]}) == project
    assert repo.count_documents("payments", {}) == 0


def test_legacy_approved_test_payment_recovers_project_without_another_charge(owned_project, monkeypatch):
    repo, project, user = owned_project
    service = IntegrationPaymentService(repository=repo)
    monkeypatch.setattr(
        gateways,
        "create_test_checkout",
        lambda *a, **kw: {"gatewayUrl": "https://webpay3gint.transbank.cl/x", "gatewayToken": "token"},
    )
    payment = service.create_integration_checkout(
        CreateCheckoutRequest(
            termsAccepted=True,
            termsVersion=WEBSITE_TERMS["version"],
            projectType="website",
            projectId=project["id"],
            provider="transbank",
        ),
        user,
    )
    payment["status"] = "paid"
    service._save(payment)
    monkeypatch.setattr(
        gateways,
        "verify_test_payment",
        lambda *a, **kw: pytest.fail("An existing approval must not trigger another charge"),
    )
    result = service.read_integration_payment(payment["id"], "transbank", user)
    assert result["finalUrl"] and result["testMode"]
    assert (
        repo.find_document(CUSTOMER_WEBSITE_CONFIG.collection, {"id": project["id"]})["customerStatus"] == "published"
    )


def test_test_payment_with_custom_domain_is_paid_while_domain_is_configured(owned_project, monkeypatch):
    repo, project, user = owned_project
    service = IntegrationPaymentService(repository=repo)
    monkeypatch.setattr(
        gateways,
        "create_test_checkout",
        lambda *a, **kw: {"gatewayUrl": "https://webpay3gint.transbank.cl/x", "gatewayToken": "token"},
    )
    payment = service.create_integration_checkout(
        CreateCheckoutRequest(
            termsAccepted=True,
            termsVersion=WEBSITE_TERMS["version"],
            projectType="website",
            projectId=project["id"],
            provider="transbank",
            withCustomDomain=True,
        ),
        user,
    )
    monkeypatch.setattr(
        gateways, "verify_test_payment", lambda *a, **kw: {"status": "paid", "providerPaymentId": "token"}
    )
    service.read_integration_payment(payment["id"], "transbank", user)
    stored = repo.find_document(CUSTOMER_WEBSITE_CONFIG.collection, {"id": project["id"]})
    assert stored["customerStatus"] == "paid"
    assert stored["payment"]["testMode"] is True
    assert not stored.get("publishedSnapshotId")


@pytest.mark.parametrize(
    "fields,code",
    [
        ({}, "TERMS_ACCEPTANCE_REQUIRED"),
        ({"termsAccepted": False, "termsVersion": WEBSITE_TERMS["version"]}, "TERMS_ACCEPTANCE_REQUIRED"),
        ({"termsAccepted": True, "termsVersion": "old-version"}, "TERMS_VERSION_MISMATCH"),
        ({"termsAccepted": True}, "TERMS_VERSION_MISMATCH"),
    ],
)
def test_terms_required_before_gateway_or_payment_is_created(owned_project, monkeypatch, fields, code):
    repo, project, user = owned_project
    calls = []
    monkeypatch.setattr(gateways, "create_test_checkout", lambda *a, **kw: calls.append(a))
    before = deepcopy(repo.find_document(CUSTOMER_WEBSITE_CONFIG.collection, {"id": project["id"]}))
    service = IntegrationPaymentService(repository=repo)
    with pytest.raises(NuvlyError) as error:
        service.create_integration_checkout(
            CreateCheckoutRequest(projectType="website", projectId=project["id"], provider="transbank", **fields), user
        )
    assert error.value.code == code
    assert calls == []
    assert repo.find_document(CUSTOMER_WEBSITE_CONFIG.collection, {"id": project["id"]}) == before


def test_accepted_document_is_stored_and_returned_with_authenticated_identity(owned_project, monkeypatch):
    from app.modules.payments.schemas import CreateCheckoutResponse, ManualPaymentConfirmationResponse
    from app.modules.payments.terms import website_terms_document

    repo, project, user = owned_project
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
    monkeypatch.setattr(gateways, "verify_test_payment", lambda *a, **kw: {"status": "pending"})
    service = IntegrationPaymentService(repository=repo)
    payload = CreateCheckoutRequest(
        projectType="website",
        projectId=project["id"],
        provider="transbank",
        termsAccepted=True,
        termsVersion=WEBSITE_TERMS["version"],
        acceptedAt="spoofed",
        customerId="attacker",
    )
    payment = service.create_integration_checkout(payload, user)
    stored = repo.find_document("payments", {"id": payment["id"]})
    acceptance = stored["termsAcceptance"]
    assert acceptance["customerId"] == user["id"]
    assert acceptance["customerEmail"] == user["email"]
    assert acceptance["acceptedAt"] == stored["createdAt"]
    assert acceptance["document"] == website_terms_document()
    assert acceptance["amount"] == stored["amount"]
    assert acceptance["billingTerms"] == stored["billingTerms"]
    document = website_terms_document()
    document["sections"][0]["text"] = "Changed locally"
    assert acceptance["document"] != document
    # New versions must not change the copy returned for an earlier payment.
    monkeypatch.setitem(WEBSITE_TERMS, "version", "future-version")
    response = service.read_integration_payment(payment["id"], "transbank", user)
    assert response["termsAcceptance"] == acceptance
    assert response["projectTitle"] == project["title"]
    assert response["withCustomDomain"] is False
    assert response["basePrice"] == stored["basePrice"]
    assert CreateCheckoutResponse(**payment).termsAcceptance == acceptance
    assert ManualPaymentConfirmationResponse(**response).termsAcceptance == acceptance
    monkeypatch.setattr(
        gateways,
        "verify_test_payment",
        lambda *a, **kw: pytest.fail("A PDF download must not verify or change a payment"),
    )
    assert service.accepted_terms_payment(payment["id"], "transbank", user)["termsAcceptance"] == acceptance
    with pytest.raises(NuvlyError):
        service.accepted_terms_payment(payment["id"], "transbank", {"id": "other", "email": "other@example.test"})
    stored["termsAcceptance"] = None
    service._save(stored)
    with pytest.raises(NuvlyError) as missing:
        service.accepted_terms_payment(payment["id"], "transbank", user)
    assert missing.value.code == "ACCEPTED_TERMS_NOT_FOUND"


def test_invalid_mp_notification_does_not_approve_anything(settings):
    service = IntegrationPaymentService(repository=InMemoryDomainRepository())
    with pytest.raises(NuvlyError):
        service.mercadopago_notification("123", "", "request-test")
    settings.mercadopago_test_webhook_secret = SecretStr("webhook-test")
    with pytest.raises(NuvlyError):
        service.mercadopago_notification("123", "ts=1,v1=invalid", "request-test")


def test_webpay_return_is_idempotent_and_rejects_wrong_cancel_token(owned_project, monkeypatch):
    repo, project, user = owned_project
    service = IntegrationPaymentService(repository=repo)
    monkeypatch.setattr(
        gateways,
        "create_test_checkout",
        lambda *a, **kw: {
            "gatewayUrl": "https://webpay3gint.transbank.cl/x",
            "gatewayToken": "token",
            "gatewayOrder": "order",
            "redirectFields": {"token_ws": "token"},
        },
    )
    payment = service.create_integration_checkout(
        CreateCheckoutRequest(
            termsAccepted=True,
            termsVersion=WEBSITE_TERMS["version"],
            projectType="website",
            projectId=project["id"],
            provider="transbank",
        ),
        user,
    )
    with pytest.raises(NuvlyError):
        service.handle_return("transbank", payment["id"], {"TBK_TOKEN": "wrong"})
    calls = []
    monkeypatch.setattr(
        gateways,
        "verify_test_payment",
        lambda *a, **kw: calls.append(kw) or {"status": "paid", "providerPaymentId": "token"},
    )
    url = service.handle_return("transbank", payment["id"], {"token_ws": "token"})
    assert url.endswith("?returned=1")
    assert calls == [{"commit": True}]
    service.handle_return("transbank", payment["id"], {"token_ws": "token"})
    assert len(calls) == 1


def test_signed_mp_webhook_fetches_provider_before_approving(owned_project, settings, monkeypatch):
    repo, project, user = owned_project
    service = IntegrationPaymentService(repository=repo)
    settings.mercadopago_test_access_token = SecretStr("TEST-example")
    settings.mercadopago_test_webhook_secret = SecretStr("webhook-test")
    monkeypatch.setattr(
        gateways, "create_test_checkout", lambda *a, **kw: {"gatewayUrl": "https://sandbox.mercadopago.cl/x"}
    )
    payment = service.create_integration_checkout(
        CreateCheckoutRequest(
            termsAccepted=True,
            termsVersion=WEBSITE_TERMS["version"],
            projectType="website",
            projectId=project["id"],
            provider="mercadopago",
        ),
        user,
    )
    remote = {
        "id": 123,
        "live_mode": False,
        "external_reference": payment["id"],
        "currency_id": "CLP",
        "transaction_amount": payment["amount"],
        "status": "approved",
    }
    monkeypatch.setattr(gateways, "_request", lambda *a, **kw: remote)
    stamp = str(int(time.time()))
    signature = hmac.new(b"webhook-test", f"id:123;request-id:req;ts:{stamp};".encode(), hashlib.sha256).hexdigest()
    assert service.mercadopago_notification("123", f"ts={stamp},v1={signature}", "req") == {"received": True}
    assert repo.find_document("payments", {"id": payment["id"]})["status"] == "paid"
    assert (
        repo.find_document(CUSTOMER_WEBSITE_CONFIG.collection, {"id": project["id"]})["customerStatus"] == "published"
    )


def test_existing_payment_routes_require_auth_and_no_raw_webhooks():
    from app.modules.payments.routes import router, transbank_webhook

    protected = {
        route.path for route in router.routes if getattr(route, "dependant", None) and route.dependant.dependencies
    }
    assert {"/payments/preview", "/payments/create-checkout", "/payments/{payment_id}"} <= protected
    with pytest.raises(NuvlyError) as exc:
        transbank_webhook()
    assert exc.value.code == "MANUAL_PAYMENT_CONFIRMATION_DISABLED"
