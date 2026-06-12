from __future__ import annotations

from fastapi import APIRouter, Query, Request, status

from app.modules.payments.schemas import (
    CreateCheckoutRequest,
    CreateCheckoutResponse,
    ManualPaymentConfirmationResponse,
    PaymentWebhookPayload,
)
from app.modules.payments.service import PaymentService

router = APIRouter(prefix="/payments", tags=["payments"])
service = PaymentService()


@router.post("/create-checkout", response_model=CreateCheckoutResponse, status_code=status.HTTP_200_OK)
def create_checkout(payload: CreateCheckoutRequest, request: Request):
    return service.create_checkout(payload, base_url=str(request.base_url).rstrip("/"))


@router.get("/{payment_id}", response_model=ManualPaymentConfirmationResponse, status_code=status.HTTP_200_OK)
def confirm_payment_temporarily(payment_id: str, provider: str = Query(...)):
    # Temporary confirmation endpoint while payment provider integrations are not connected.
    return service.confirm_payment_manually(payment_id, provider)


@router.post("/webhooks/mercadopago")
def mercadopago_webhook(payload: PaymentWebhookPayload):
    return service.process_webhook("mercadopago", payload)


@router.post("/webhooks/transbank")
def transbank_webhook(payload: PaymentWebhookPayload):
    return service.process_webhook("transbank", payload)
