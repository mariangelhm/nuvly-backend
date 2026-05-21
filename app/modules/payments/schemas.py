from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

from app.modules.domain.schemas import PaymentStatus

ProjectType = Literal["invitation", "website"]
PaymentProvider = Literal["mercadopago", "transbank"]


class CreateCheckoutRequest(BaseModel):
    projectType: ProjectType
    projectId: str = Field(min_length=1)
    provider: PaymentProvider


class CreateCheckoutResponse(BaseModel):
    paymentId: str
    projectType: ProjectType
    projectId: str
    provider: PaymentProvider
    status: PaymentStatus
    checkoutUrl: str


class PaymentWebhookPayload(BaseModel):
    paymentId: str = Field(min_length=1)
    status: Literal["approved", "failed"]
    providerPaymentId: Optional[str] = None
