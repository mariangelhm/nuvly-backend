"""Shared boundary types; JSON money stays numeric and revision strings stay exact."""

from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Annotated

from pydantic import AfterValidator, BeforeValidator

MAX_SAFE_AMOUNT = 2**53 - 1


def clp_amount(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise ValueError("El importe CLP debe ser un entero no negativo.")
    try:
        amount = Decimal(str(value))
    except InvalidOperation as error:
        raise ValueError("Importe CLP inválido.") from error
    if not amount.is_finite() or amount < 0 or amount > MAX_SAFE_AMOUNT or amount != amount.to_integral_value():
        raise ValueError("El importe CLP debe ser entero, finito, no negativo y representable en JSON.")
    return int(amount)


def iso_timestamp(value: str) -> str:
    # Preserve spelling/precision: expectedUpdatedAt is an opaque CAS revision.
    if "T" not in value:
        raise ValueError("Se requiere fecha y hora ISO 8601 con zona horaria.")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("Fecha ISO 8601 inválida.") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("La fecha debe incluir zona horaria.")
    return value


CLPAmount = Annotated[int, BeforeValidator(clp_amount)]
IsoTimestamp = Annotated[str, AfterValidator(iso_timestamp)]
