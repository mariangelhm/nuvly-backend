from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

DiscountType = Literal["percentage", "fixed"]
DiscountAppliesTo = Literal["all", "website", "invitation"]


class AdminDiscountCodeCreateRequest(BaseModel):
    code: str = Field(min_length=1, max_length=32)
    discountType: DiscountType
    value: int = Field(gt=0)
    appliesTo: DiscountAppliesTo = "all"
    active: bool = True
    description: Optional[str] = Field(default=None, max_length=160)
    expiresAt: Optional[str] = None

    @field_validator("code")
    @classmethod
    def validate_code(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not normalized:
            raise ValueError("Discount code is required.")
        if any(char not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for char in normalized):
            raise ValueError("Discount code contains invalid characters.")
        return normalized

    @field_validator("value")
    @classmethod
    def validate_value(cls, value: int, info) -> int:
        discount_type = info.data.get("discountType")
        if discount_type == "percentage" and value > 100:
            raise ValueError("Percentage discounts cannot exceed 100.")
        return value


class AdminDiscountCodeUpdateRequest(AdminDiscountCodeCreateRequest):
    pass


class AdminDiscountCodeActiveUpdate(BaseModel):
    active: bool


class AdminDiscountCodeResponse(BaseModel):
    id: str
    code: str
    discountType: DiscountType
    value: int
    appliesTo: DiscountAppliesTo
    active: bool
    description: Optional[str] = None
    expiresAt: Optional[str] = None
    createdAt: str
    updatedAt: str
