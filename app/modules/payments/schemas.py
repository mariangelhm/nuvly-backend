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
    withCustomDomain: bool = False
    customDomain: Optional[str] = None
    discountCode: Optional[str] = Field(default=None, min_length=1, max_length=32)


class CheckoutPreviewRequest(BaseModel):
    projectType: ProjectType
    projectId: str = Field(min_length=1)
    withCustomDomain: bool = False
    customDomain: Optional[str] = None
    discountCode: Optional[str] = Field(default=None, min_length=1, max_length=32)


class CheckoutPreviewResponse(BaseModel):
    projectType: ProjectType
    projectId: str
    amount: float
    subtotalAmount: float
    discountAmount: int = 0
    discountCode: Optional[str] = None
    discountType: Optional[str] = None
    discountValue: Optional[int] = None
    currency: str
    withCustomDomain: bool
    customDomain: Optional[str] = None
    customDomainSurcharge: int = 0
    domainOptionExplanation: Optional[str] = None


class CreateCheckoutResponse(BaseModel):
    paymentId: str
    projectType: ProjectType
    projectId: str
    provider: PaymentProvider
    status: PaymentStatus
    amount: float
    subtotalAmount: float
    discountAmount: int = 0
    discountCode: Optional[str] = None
    discountType: Optional[str] = None
    discountValue: Optional[int] = None
    currency: str
    checkoutUrl: str
    withCustomDomain: bool
    customDomain: Optional[str] = None
    customDomainSurcharge: int = 0
    domainOptionExplanation: Optional[str] = None


class PaymentWebhookPayload(BaseModel):
    paymentId: str = Field(min_length=1)
    status: Literal["approved", "failed"]
    providerPaymentId: Optional[str] = None


class ManualPaymentConfirmationResponse(BaseModel):
    ok: bool = True
    message: str
    paymentId: str
    provider: PaymentProvider
    status: PaymentStatus
    projectType: Optional[ProjectType] = None
    projectId: Optional[str] = None
    amount: Optional[float] = None
    subtotalAmount: Optional[float] = None
    discountAmount: Optional[int] = None
    discountCode: Optional[str] = None
    currency: Optional[str] = None
    finalUrl: Optional[str] = None
    websiteUrl: Optional[str] = None
    invitationUrl: Optional[str] = None
