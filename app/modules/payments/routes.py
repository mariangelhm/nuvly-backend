from __future__ import annotations

from fastapi import APIRouter, Request, status

from app.modules.payments.schemas import CreateCheckoutRequest, CreateCheckoutResponse, PaymentWebhookPayload
from app.modules.payments.service import PaymentService

router = APIRouter(prefix="/payments", tags=["payments"])
service = PaymentService()


@router.post("/create-checkout", response_model=CreateCheckoutResponse, status_code=status.HTTP_200_OK)
def create_checkout(payload: CreateCheckoutRequest, request: Request):
    return service.create_checkout(payload, base_url=str(request.base_url).rstrip("/"))


@router.post("/webhooks/mercadopago")
def mercadopago_webhook(payload: PaymentWebhookPayload):
    return service.process_webhook("mercadopago", payload)


@router.post("/webhooks/transbank")
def transbank_webhook(payload: PaymentWebhookPayload):
    return service.process_webhook("transbank", payload)
