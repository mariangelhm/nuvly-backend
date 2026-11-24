from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import RedirectResponse, Response
from starlette.concurrency import run_in_threadpool

from app.core.config import get_settings
from app.core.errors import NuvlyError
from app.modules.auth.dependencies import get_current_user
from app.modules.payments.integration_service import IntegrationPaymentService
from app.modules.payments.production_service import WebpayProductionService
from app.modules.payments.receipt_pdf import render_accepted_terms_pdf
from app.modules.payments.schemas import (
    CheckoutPreviewRequest,
    CheckoutPreviewResponse,
    CreateCheckoutRequest,
    CreateCheckoutResponse,
    ManualPaymentConfirmationResponse,
    PaymentProvider,
)
from app.modules.payments.terms import website_terms_document

router = APIRouter(prefix="/payments", tags=["payments"])
service = (
    WebpayProductionService() if get_settings().payments_environment == "production" else IntegrationPaymentService()
)


@router.get("/terms/website")
def website_terms():
    return website_terms_document()


@router.get("/providers")
def providers():
    return service.providers()


@router.post("/preview", response_model=CheckoutPreviewResponse)
def preview_checkout(payload: CheckoutPreviewRequest, user: dict = Depends(get_current_user)):
    service.assert_project_owner(payload.projectType, payload.projectId, user)
    return service.preview_checkout(payload)


@router.post("/create-checkout", response_model=CreateCheckoutResponse)
def create_checkout(payload: CreateCheckoutRequest, request: Request, user: dict = Depends(get_current_user)):
    return service.create_integration_checkout(payload, user, base_url=str(request.base_url).rstrip("/"))


@router.get("/{payment_id}", response_model=ManualPaymentConfirmationResponse)
def get_payment(payment_id: str, provider: PaymentProvider = Query(...), user: dict = Depends(get_current_user)):
    return service.read_integration_payment(payment_id, provider, user)


@router.get("/{payment_id}/accepted-terms.pdf")
def accepted_terms_pdf(payment_id: str, provider: PaymentProvider = Query(...), user: dict = Depends(get_current_user)):
    payment = service.accepted_terms_payment(payment_id, provider, user)
    return Response(
        content=render_accepted_terms_pdf(payment),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="nuvly-condiciones-{payment["id"]}.pdf"',
            "Cache-Control": "private, no-store",
        },
    )


@router.post("/{payment_id}/receipt-email")
def retry_receipt_email(
    payment_id: str, provider: PaymentProvider = Query(...), user: dict = Depends(get_current_user)
):
    return service.retry_receipt_email(payment_id, provider, user)


@router.get("/return/{provider}/{payment_id}", operation_id="payment_return_get")
@router.post("/return/{provider}/{payment_id}", operation_id="payment_return_post")
async def payment_return(provider: PaymentProvider, payment_id: str, request: Request):
    params = dict(request.query_params)
    if request.method == "POST":
        params.update(dict(await request.form()))
    url = await run_in_threadpool(service.handle_return, provider, payment_id, params)
    return RedirectResponse(url, status_code=303)


@router.post("/webhooks/mercadopago")
async def mercadopago_webhook(request: Request):
    return await run_in_threadpool(
        service.mercadopago_notification,
        request.query_params.get("data.id"),
        request.headers.get("x-signature"),
        request.headers.get("x-request-id"),
    )


@router.post("/webhooks/transbank")
def transbank_webhook():
    raise NuvlyError(
        "Webpay se verifica mediante su retorno y la API de Transbank; no acepta confirmaciones manuales.",
        410,
        "MANUAL_PAYMENT_CONFIRMATION_DISABLED",
    )
