"""Explicitly enabled Webpay production adapter; sandbox remains isolated."""

from decimal import Decimal
from urllib.parse import quote, urlparse

from app.core.config import get_settings
from app.core.errors import NuvlyError
from app.modules.payments import gateways
from app.modules.payments.integration_service import IntegrationPaymentService

TRANSACTIONS_URL = "https://webpay3g.transbank.cl/rswebpaytransaction/api/webpay/v1.2/transactions"


class WebpayProductionService(IntegrationPaymentService):
    environment = "production"
    test_mode = False

    def _assert_mode(self):
        settings = get_settings()
        if settings.payments_environment != "production" or not settings.payments_production_enabled:
            raise NuvlyError("El cobro productivo no está habilitado.", 503, "PAYMENTS_PRODUCTION_DISABLED")
        key = settings.transbank_api_key
        if (
            not settings.transbank_commerce_code
            or not key
            or not key.get_secret_value().strip()
            or settings.transbank_commerce_code == gateways.TBK_CODE
            or key.get_secret_value() == gateways.TBK_KEY
        ):
            raise NuvlyError("Configura credenciales productivas de Webpay.", 503, "PRODUCTION_GATEWAY_NOT_CONFIGURED")
        for base in (settings.public_base_url, settings.frontend_public_base_url):
            url = urlparse(base or "")
            if url.scheme != "https" or not url.hostname or url.username or url.password:
                raise NuvlyError(
                    "Producción requiere URLs públicas HTTPS del backend y frontend.", 503, "PRODUCTION_URL_REQUIRED"
                )

    def providers(self):
        try:
            self._assert_mode()
            enabled = True
        except NuvlyError:
            enabled = False
        return {
            "environment": self.environment,
            "testMode": False,
            "providers": [
                {
                    "id": "transbank",
                    "label": "Webpay Plus · Transbank",
                    "enabled": enabled,
                    "helper": "Pago seguro con Webpay" if enabled else "Pagos temporalmente no disponibles",
                },
            ],
        }

    def _headers(self):
        self._assert_mode()
        settings = get_settings()
        return {
            "Tbk-Api-Key-Id": settings.transbank_commerce_code,
            "Tbk-Api-Key-Secret": settings.transbank_api_key.get_secret_value(),
            "Content-Type": "application/json",
        }

    def _create_gateway(self, provider, payment, callback, notification_url=None):
        self._assert_mode()
        if provider != "transbank":
            raise NuvlyError("Proveedor productivo no disponible.", 400, "INVALID_PAYMENT_PROVIDER")
        amount = Decimal(str(payment["amount"]))
        if not amount.is_finite() or amount <= 0 or amount != amount.to_integral_value():
            raise NuvlyError("El monto debe ser positivo y entero en CLP.", 400, "INVALID_PAYMENT_AMOUNT")
        if urlparse(callback).scheme != "https":
            raise NuvlyError("Retorno productivo inválido.", 400, "PRODUCTION_URL_REQUIRED")
        result = gateways._request(
            "POST",
            TRANSACTIONS_URL,
            self._headers(),
            {
                "buy_order": payment["id"][:26],
                "session_id": payment["id"],
                "amount": int(amount),
                "return_url": callback,
            },
        )
        url = urlparse(result.get("url") or "")
        if (
            not result.get("token")
            or url.scheme != "https"
            or url.hostname != "webpay3g.transbank.cl"
            or url.username
            or url.password
        ):
            raise NuvlyError("Webpay no devolvió una dirección productiva válida.", 502, "INVALID_PRODUCTION_CHECKOUT")
        return {
            "gatewayUrl": url.geturl(),
            "redirectMethod": "POST",
            "redirectFields": {"token_ws": result["token"]},
            "gatewayToken": result["token"],
            "gatewayOrder": payment["id"][:26],
        }

    def _verify_gateway(self, payment, resource_id=None, commit=False):
        self._assert_mode()
        token = payment.get("gatewayToken")
        if (
            payment.get("environment") != "production"
            or payment.get("testMode") is not False
            or payment.get("provider") != "transbank"
        ):
            raise NuvlyError("El pago no pertenece a este ambiente.", 400, "INVALID_PAYMENT_ENVIRONMENT")
        if not token or (resource_id is not None and resource_id != token):
            raise NuvlyError("El token no corresponde a esta orden.", 400, "PAYMENT_TOKEN_MISMATCH")
        result = gateways._request(
            "PUT" if commit else "GET",
            TRANSACTIONS_URL + "/" + quote(token, safe=""),
            self._headers(),
            {} if commit else None,
        )
        if (
            str(result.get("buy_order")) != payment.get("gatewayOrder")
            or str(result.get("session_id")) != payment["id"]
            or Decimal(str(result.get("amount", -1))) != Decimal(str(payment["amount"]))
        ):
            raise NuvlyError("La confirmación no coincide con la orden.", 409, "PAYMENT_VERIFICATION_MISMATCH")
        approved = result.get("status") == "AUTHORIZED" and result.get("response_code") == 0
        failed = result.get("status") in {"FAILED", "REVERSED", "NULLIFIED", "PARTIALLY_NULLIFIED"} or (
            "response_code" in result and result["response_code"] != 0
        )
        return {"status": "paid" if approved else "failed" if failed else "pending", "providerPaymentId": token}

    def _summary(self, payment):
        summary = super()._summary(payment)
        summary.update(
            environment="production",
            testMode=False,
            message="Pago aprobado."
            if payment["status"] == "paid"
            else "El pago no se completó."
            if payment["status"] == "failed"
            else "Pago pendiente de confirmación.",
        )
        return summary

    def mercadopago_notification(self, resource_id, signature, request_id):
        raise NuvlyError("Este ambiente no recibe notificaciones de Mercado Pago.", 403, "INVALID_PAYMENT_PROVIDER")
