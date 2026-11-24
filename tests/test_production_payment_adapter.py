from types import SimpleNamespace

import pytest
from pydantic import SecretStr

from app.core.errors import NuvlyError
from app.modules.payments import production_service as module
from app.modules.payments.production_service import TRANSACTIONS_URL, WebpayProductionService


@pytest.fixture
def production(monkeypatch):
    settings = SimpleNamespace(
        payments_environment="production",
        payments_production_enabled=True,
        transbank_commerce_code="merchant-synthetic",
        transbank_api_key=SecretStr("synthetic-production-key"),
        public_base_url="https://api.example.test",
        frontend_public_base_url="https://example.test",
    )
    monkeypatch.setattr(module, "get_settings", lambda: settings)
    return settings, WebpayProductionService()


def test_production_callback_applies_publication_once_without_real_charge(production, monkeypatch):
    from test_payments_flow import InMemoryDomainRepository, _create_customer_project

    from app.modules.domain.services import CUSTOMER_WEBSITE_CONFIG
    from app.modules.payments import integration_service
    from app.modules.payments.schemas import CreateCheckoutRequest
    from app.modules.payments.terms import WEBSITE_TERMS

    settings, _ = production
    settings.api_prefix = "/api"
    settings.mercadopago_test_webhook_secret = None
    monkeypatch.setattr(integration_service, "get_settings", lambda: settings)
    repo = InMemoryDomainRepository()
    project = _create_customer_project(repo)
    project["ownerId"] = "owner"
    repo.replace_document(CUSTOMER_WEBSITE_CONFIG.collection, project["id"], project, "missing", "missing", "duplicate")
    service = WebpayProductionService(repository=repo)
    monkeypatch.setattr(service, "_send_receipt", lambda *a, **kw: None)
    calls = []
    order = {}

    def gateway(method, url, headers, payload=None, **kwargs):
        calls.append(method)
        if method == "POST":
            order.update(payload)
            return {"url": "https://webpay3g.transbank.cl/checkout", "token": "synthetic-token"}
        return {**order, "status": "AUTHORIZED", "response_code": 0}

    monkeypatch.setattr(module.gateways, "_request", gateway)
    payment = service.create_integration_checkout(
        CreateCheckoutRequest(
            projectId=project["id"],
            projectType="website",
            provider="transbank",
            termsAccepted=True,
            termsVersion=WEBSITE_TERMS["version"],
        ),
        {"id": "owner", "email": "owner@example.test"},
        base_url=settings.public_base_url,
    )
    assert payment["testMode"] is False
    for _ in range(2):
        service.handle_return("transbank", payment["id"], {"token_ws": "synthetic-token"})
    stored = repo.find_document(CUSTOMER_WEBSITE_CONFIG.collection, {"id": project["id"]})
    assert stored["customerStatus"] == "published"
    assert stored["payment"]["testMode"] is False
    assert stored["payment"]["environment"] == "production"
    assert repo.count_documents(CUSTOMER_WEBSITE_CONFIG.snapshot_collection, {"sourceId": project["id"]}) == 1
    assert calls == ["POST", "PUT"]


def test_production_disabled_by_default_or_missing_config(production):
    settings, service = production
    settings.payments_production_enabled = False
    with pytest.raises(NuvlyError) as exc:
        service._assert_mode()
    assert exc.value.code == "PAYMENTS_PRODUCTION_DISABLED"
    assert service.providers()["providers"][0]["enabled"] is False


def test_production_never_uses_integration_credentials(production):
    settings, service = production
    settings.transbank_commerce_code = module.gateways.TBK_CODE
    with pytest.raises(NuvlyError):
        service._assert_mode()


def test_production_creation_uses_only_live_host_and_configured_credentials(production, monkeypatch):
    settings, service = production
    calls = []

    def request(*args, **kwargs):
        calls.append(args)
        return {"url": "https://webpay3g.transbank.cl/checkout", "token": "synthetic-token"}

    monkeypatch.setattr(module.gateways, "_request", request)
    result = service._create_gateway(
        "transbank", {"id": "pay_synthetic", "amount": 1000}, "https://api.example.test/return"
    )
    assert calls[0][1] == TRANSACTIONS_URL
    assert calls[0][2]["Tbk-Api-Key-Id"] == settings.transbank_commerce_code
    assert result["redirectMethod"] == "POST"
    assert service.providers()["testMode"] is False


@pytest.mark.parametrize(
    "patch,accepted",
    [
        ({}, True),
        ({"amount": 1}, False),
        ({"session_id": "another-payment"}, False),
        ({"status": "FAILED", "response_code": -1}, True),
    ],
)
def test_production_approval_requires_matching_provider_order_and_amount(production, monkeypatch, patch, accepted):
    _, service = production
    payment = {
        "id": "pay_synthetic",
        "environment": "production",
        "testMode": False,
        "provider": "transbank",
        "amount": 1000,
        "gatewayToken": "token",
        "gatewayOrder": "order",
    }
    response = {
        "session_id": payment["id"],
        "buy_order": "order",
        "amount": 1000,
        "status": "AUTHORIZED",
        "response_code": 0,
        **patch,
    }
    monkeypatch.setattr(module.gateways, "_request", lambda *a, **k: response)
    if accepted:
        assert service._verify_gateway(payment, "token")["status"] == ("failed" if patch else "paid")
    else:
        with pytest.raises(NuvlyError) as exc:
            service._verify_gateway(payment, "token")
        assert exc.value.code == "PAYMENT_VERIFICATION_MISMATCH"


def test_production_rejects_sandbox_record_before_provider_io(production, monkeypatch):
    _, service = production
    monkeypatch.setattr(module.gateways, "_request", lambda *a, **k: pytest.fail("No external call allowed"))
    with pytest.raises(NuvlyError):
        service._verify_gateway({"environment": "integration", "testMode": True, "provider": "transbank"})
