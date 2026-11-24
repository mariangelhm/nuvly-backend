"""Hosted payment integrations restricted to UAT. No production gateway is supported."""

from decimal import Decimal
from urllib.parse import quote, urlparse

import requests

from app.core.config import get_settings
from app.core.errors import NuvlyError

# Public integration credentials published by Transbank's official Python SDK.
TBK_CODE = "597055555532"
TBK_KEY = "579B532A7440BB0C9079DED94D31EA1615BACEB56610332264630D42D0A36B1C"
TBK_URL = "https://webpay3gint.transbank.cl/rswebpaytransaction/api/webpay/v1.2/transactions"
MP_URL = "https://api.mercadopago.com"


def assert_integration_mode():
    settings = get_settings()
    if settings.payments_environment != "integration" or settings.app_env.lower() in ("production", "prod"):
        raise NuvlyError(
            "Los pagos están habilitados únicamente en ambiente de integración/UAT.",
            503,
            "PAYMENTS_PRODUCTION_DISABLED",
        )


def _request(method, url, headers, payload=None, params=None):
    try:
        response = requests.request(
            method, url, headers=headers, json=payload, params=params, timeout=(5, 20), allow_redirects=False
        )
        if not 200 <= response.status_code < 300:
            raise NuvlyError(
                "El proveedor de pruebas no pudo procesar la solicitud. Revisa la configuración e inténtalo nuevamente.",
                502,
                "PAYMENT_GATEWAY_ERROR",
            )
        data = response.json()
        if not isinstance(data, dict):
            raise ValueError("Invalid gateway response")
        return data
    except (requests.RequestException, ValueError) as exc:
        raise NuvlyError(
            "No fue posible conectar con el proveedor de pruebas.", 502, "PAYMENT_GATEWAY_UNAVAILABLE"
        ) from exc


def _tbk_headers():
    return {"Tbk-Api-Key-Id": TBK_CODE, "Tbk-Api-Key-Secret": TBK_KEY, "Content-Type": "application/json"}


def _mp_headers():
    secret = get_settings().mercadopago_test_access_token
    token = secret.get_secret_value().strip() if secret else ""
    if not token:
        raise NuvlyError(
            "Configura MERCADOPAGO_TEST_ACCESS_TOKEN en el backend para probar Mercado Pago.",
            503,
            "MERCADOPAGO_TEST_NOT_CONFIGURED",
        )
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    # Test-seller accounts may receive APP_USR credentials. Only permit these
    # after confirming with Mercado Pago that they belong to a test account.
    if not token.startswith("TEST-"):
        user = _request("GET", MP_URL + "/users/me", headers)
        if "test_user" not in user.get("tags", []) or user.get("site_id") != "MLC":
            raise NuvlyError(
                "Usa credenciales de prueba de Chile, no credenciales de un vendedor real.",
                400,
                "MERCADOPAGO_TEST_ACCOUNT_REQUIRED",
            )
    return headers


def _checkout_url(url, provider):
    parsed = urlparse(url or "")
    hosts = {
        "transbank": {"webpay3gint.transbank.cl"},
        "mercadopago": {"sandbox.mercadopago.cl", "sandbox.mercadopago.com"},
    }
    if parsed.scheme != "https" or parsed.hostname not in hosts[provider] or parsed.username or parsed.password:
        raise NuvlyError("El proveedor no devolvió un checkout de pruebas válido.", 502, "INVALID_TEST_CHECKOUT_URL")
    return url


def create_test_checkout(provider, payment, callback_url, notification_url=None):
    assert_integration_mode()
    amount = Decimal(str(payment["amount"]))
    if amount <= 0 or amount != amount.to_integral_value():
        raise NuvlyError(
            "El pago de prueba requiere un monto positivo en pesos chilenos enteros.",
            400,
            "INVALID_TEST_PAYMENT_AMOUNT",
        )
    if provider == "transbank":
        result = _request(
            "POST",
            TBK_URL,
            _tbk_headers(),
            {
                "buy_order": payment["id"][:26],
                "session_id": payment["id"],
                "amount": int(amount),
                "return_url": callback_url,
            },
        )
        if not result.get("token"):
            raise NuvlyError("Webpay no devolvió el token de integración.", 502, "INVALID_TEST_CHECKOUT")
        return {
            "gatewayUrl": _checkout_url(result.get("url"), provider),
            "redirectMethod": "POST",
            "redirectFields": {"token_ws": result["token"]},
            "gatewayToken": result["token"],
            "gatewayOrder": payment["id"][:26],
        }
    if provider != "mercadopago":
        raise NuvlyError("Proveedor no soportado.", 400, "INVALID_PAYMENT_PROVIDER")
    data = {
        "items": [
            {
                "id": payment["projectId"],
                "title": payment.get("title") or "Proyecto Nuvly · prueba",
                "quantity": 1,
                "currency_id": "CLP",
                "unit_price": int(amount),
            }
        ],
        "external_reference": payment["id"],
        "back_urls": {key: callback_url for key in ("success", "failure", "pending")},
    }
    if callback_url.startswith("https://"):
        data["auto_return"] = "approved"
    if notification_url:
        data["notification_url"] = notification_url
    result = _request(
        "POST", MP_URL + "/checkout/preferences", {**_mp_headers(), "X-Idempotency-Key": payment["id"]}, data
    )
    if not result.get("id"):
        raise NuvlyError("Mercado Pago no devolvió la preferencia de pruebas.", 502, "INVALID_TEST_CHECKOUT")
    return {
        "gatewayUrl": _checkout_url(result.get("sandbox_init_point"), provider),
        "redirectMethod": "GET",
        "redirectFields": {},
        "gatewayPreferenceId": result["id"],
    }


def verify_test_payment(payment, resource_id=None, commit=False):
    assert_integration_mode()
    if payment.get("environment") != "integration":
        raise NuvlyError("Este pago no pertenece al entorno de pruebas.", 400, "INVALID_PAYMENT_ENVIRONMENT")
    if payment["provider"] == "transbank":
        token = payment.get("gatewayToken")
        if not token or (resource_id is not None and resource_id != token):
            raise NuvlyError("El token de retorno no corresponde al pago.", 400, "PAYMENT_TOKEN_MISMATCH")
        result = _request(
            "PUT" if commit else "GET", TBK_URL + "/" + quote(token, safe=""), _tbk_headers(), {} if commit else None
        )
        if (
            str(result.get("buy_order")) != payment.get("gatewayOrder")
            or str(result.get("session_id")) != payment["id"]
            or Decimal(str(result.get("amount", -1))) != Decimal(str(payment["amount"]))
        ):
            raise NuvlyError("Los datos de Webpay no coinciden con la orden.", 409, "PAYMENT_VERIFICATION_MISMATCH")
        approved = result.get("status") == "AUTHORIZED" and result.get("response_code") == 0
        failed = result.get("status") in ("FAILED", "REVERSED", "NULLIFIED", "PARTIALLY_NULLIFIED") or (
            "response_code" in result and result["response_code"] != 0
        )
        return {"status": "paid" if approved else "failed" if failed else "pending", "providerPaymentId": token}
    headers = _mp_headers()
    if resource_id:
        if not str(resource_id).isdigit():
            raise NuvlyError("Identificador de pago de prueba inválido.", 400, "INVALID_PROVIDER_PAYMENT_ID")
        result = _request("GET", MP_URL + "/v1/payments/" + str(resource_id), headers)
    else:
        found = _request(
            "GET",
            MP_URL + "/v1/payments/search",
            headers,
            params={"external_reference": payment["id"], "sort": "date_created", "criteria": "desc"},
        )
        results = found.get("results") or []
        # An approved retry wins over a previous declined attempt.
        result = next((item for item in results if item.get("status") == "approved"), results[0] if results else None)
        if result is None:
            return {"status": "pending", "providerPaymentId": None}
    if (
        result.get("live_mode") is not False
        or str(result.get("external_reference")) != payment["id"]
        or result.get("currency_id") != "CLP"
        or Decimal(str(result.get("transaction_amount", -1))) != Decimal(str(payment["amount"]))
    ):
        raise NuvlyError(
            "El pago no es una transacción de prueba válida para esta orden.", 409, "PAYMENT_VERIFICATION_MISMATCH"
        )
    status = result.get("status")
    return {
        "status": "paid"
        if status == "approved"
        else "failed"
        if status in ("rejected", "cancelled", "refunded", "charged_back")
        else "pending",
        "providerPaymentId": str(result["id"]),
    }
