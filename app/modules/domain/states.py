"""Shared state vocabulary for DTOs and persisted document validation."""

from typing import Literal, get_args

TemplateStatus = Literal["draft", "private_preview", "published", "unpublished", "deprecated", "archived"]
CustomerStatus = Literal[
    "draft", "temporary", "editing", "abandoned", "pending_payment", "payment_failed", "paid", "published", "cancelled"
]
PaymentStatus = Literal["unpaid", "pending", "paid", "failed", "refunded"]

DOCUMENT_STATES = {
    "templateStatus": frozenset(get_args(TemplateStatus)),
    "customerStatus": frozenset(get_args(CustomerStatus)),
}
