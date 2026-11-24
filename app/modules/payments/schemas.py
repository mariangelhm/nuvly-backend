from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, JsonValue, StrictBool

from app.core.value_types import CLPAmount
from app.modules.domain.states import PaymentStatus

ProjectType = Literal["invitation", "website"]
PaymentProvider = Literal["mercadopago", "transbank"]


class CreateCheckoutRequest(BaseModel):
    termsAccepted: StrictBool = False
    termsVersion: Optional[str] = None
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
    billingTerms: Optional[dict[str, JsonValue]] = None
    projectType: ProjectType
    projectId: str
    amount: CLPAmount
    subtotalAmount: CLPAmount
    basePrice: CLPAmount = 0
    extrasTotal: CLPAmount = 0
    discountAmount: CLPAmount = 0
    discountCode: Optional[str] = None
    discountType: Optional[str] = None
    discountValue: Optional[int] = None
    currency: str
    withCustomDomain: bool
    customDomain: Optional[str] = None
    customDomainSurcharge: CLPAmount = 0
    domainOptionExplanation: Optional[str] = None


class CreateCheckoutResponse(BaseModel):
    termsAcceptance: Optional[dict[str, JsonValue]] = None
    billingTerms: Optional[dict[str, JsonValue]] = None
    environment: str = "integration"
    testMode: bool = True
    gatewayUrl: Optional[str] = None
    redirectMethod: str = "GET"
    redirectFields: dict[str, str] = Field(default_factory=dict)
    paymentId: str
    projectType: ProjectType
    projectId: str
    provider: PaymentProvider
    status: PaymentStatus
    amount: CLPAmount
    subtotalAmount: CLPAmount
    discountAmount: CLPAmount = 0
    discountCode: Optional[str] = None
    discountType: Optional[str] = None
    discountValue: Optional[int] = None
    currency: str
    checkoutUrl: str
    withCustomDomain: bool
    customDomain: Optional[str] = None
    customDomainSurcharge: CLPAmount = 0
    domainOptionExplanation: Optional[str] = None


class PaymentWebhookPayload(BaseModel):
    paymentId: str = Field(min_length=1)
    status: Literal["approved", "failed"]
    providerPaymentId: Optional[str] = None


class ManualPaymentConfirmationResponse(BaseModel):
    receiptEmail: Optional[dict[str, JsonValue]] = None
    projectTitle: Optional[str] = None
    publicSlug: Optional[str] = None
    planTier: Optional[str] = None
    basePrice: Optional[CLPAmount] = None
    extrasTotal: Optional[CLPAmount] = None
    billingTerms: Optional[dict[str, JsonValue]] = None
    withCustomDomain: bool = False
    customDomain: Optional[str] = None
    customDomainSurcharge: CLPAmount = 0
    termsAcceptance: Optional[dict[str, JsonValue]] = None
    ok: Optional[bool] = None
    environment: Optional[str] = None
    testMode: bool = False
    checkoutUrl: Optional[str] = None
    gatewayUrl: Optional[str] = None
    redirectMethod: str = "GET"
    redirectFields: dict[str, str] = Field(default_factory=dict)
    message: str
    paymentId: str
    provider: PaymentProvider
    status: PaymentStatus
    projectType: Optional[ProjectType] = None
    projectId: Optional[str] = None
    amount: Optional[CLPAmount] = None
    subtotalAmount: Optional[CLPAmount] = None
    discountAmount: Optional[CLPAmount] = None
    discountCode: Optional[str] = None
    currency: Optional[str] = None
    finalUrl: Optional[str] = None
    websiteUrl: Optional[str] = None
    invitationUrl: Optional[str] = None
