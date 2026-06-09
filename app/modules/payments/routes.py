from __future__ import annotations

from fastapi import APIRouter, status

from app.modules.payments.schemas import CreateCheckoutRequest, CreateCheckoutResponse, PaymentWebhookPayload
from app.modules.payments.service import PaymentService

router = APIRouter(prefix="/payments", tags=["payments"])
service = PaymentService()


@router.post("/create-checkout", response_model=CreateCheckoutResponse, status_code=status.HTTP_200_OK)
def create_checkout(payload: CreateCheckoutRequest):
    return service.create_checkout(payload)


@router.post("/webhooks/mercadopago")
def mercadopago_webhook(payload: PaymentWebhookPayload):
    return service.process_webhook("mercadopago", payload)


@router.post("/webhooks/transbank")
def transbank_webhook(payload: PaymentWebhookPayload):
    return service.process_webhook("transbank", payload)
