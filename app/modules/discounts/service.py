from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.core.errors import NuvlyError
from app.core.utils import new_id, utc_now_iso
from app.modules.domain.repository import DomainRepository


def _parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        normalized = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except ValueError:
        raise NuvlyError("La fecha de expiracion del codigo no es valida.", 400, "INVALID_DISCOUNT_EXPIRATION")


class DiscountCodeService:
    def __init__(self, repository=None):
        self.repository = repository or DomainRepository()

    @staticmethod
    def normalize_code(code: str) -> str:
        return code.strip().upper()

    def _collection_name(self) -> str:
        return "discount_codes"

    def list_codes(self) -> list[dict[str, Any]]:
        return self.repository.find_documents(self._collection_name(), {}, limit=0, sort_field="createdAt", sort_direction=-1)

    def create_code(self, payload) -> dict[str, Any]:
        now = utc_now_iso()
        expires_at = _parse_iso_datetime(payload.expiresAt).isoformat() if payload.expiresAt else None
        code = self.normalize_code(payload.code)
        document = {
            "id": new_id("dsc"),
            "code": code,
            "codeNormalized": code,
            "discountType": payload.discountType,
            "value": payload.value,
            "appliesTo": payload.appliesTo,
            "active": payload.active,
            "description": (payload.description or "").strip() or None,
            "expiresAt": expires_at,
            "createdAt": now,
            "updatedAt": now,
        }
        return self.repository.insert_document(
            self._collection_name(),
            document,
            duplicate_message="Ya existe un codigo de descuento con ese codigo.",
            duplicate_code="DUPLICATED_DISCOUNT_CODE",
        )

    def get_valid_code_for_checkout(self, code: str, project_type: str) -> dict[str, Any]:
        normalized = self.normalize_code(code)
        if not normalized:
            raise NuvlyError("Debes ingresar un codigo de descuento valido.", 400, "INVALID_DISCOUNT_CODE")

        discount = self.repository.find_document(self._collection_name(), {"codeNormalized": normalized})
        if not discount:
            raise NuvlyError("El codigo de descuento no existe.", 404, "DISCOUNT_CODE_NOT_FOUND")
        if not discount.get("active", False):
            raise NuvlyError("El codigo de descuento no esta activo.", 400, "DISCOUNT_CODE_INACTIVE")

        applies_to = discount.get("appliesTo", "all")
        if applies_to not in {"all", project_type}:
            raise NuvlyError("El codigo de descuento no aplica a este proyecto.", 400, "DISCOUNT_CODE_NOT_APPLICABLE")

        expires_at = _parse_iso_datetime(discount.get("expiresAt"))
        if expires_at and expires_at <= datetime.now(timezone.utc):
            raise NuvlyError("El codigo de descuento ya expiro.", 400, "DISCOUNT_CODE_EXPIRED")

        return discount

    @staticmethod
    def calculate_discount_amount(subtotal: float, discount: dict[str, Any]) -> int:
        if subtotal <= 0:
            return 0
        if discount.get("discountType") == "percentage":
            return max(int(round(subtotal * (discount.get("value", 0) / 100))), 0)
        return max(min(int(discount.get("value", 0)), int(round(subtotal))), 0)
