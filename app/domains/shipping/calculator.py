"""Pure shipping calculations shared by checkout pricing and ShippingService."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from fastapi import HTTPException, status


def _decimal(value: Any, field_name: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Invalid shipping configuration: {field_name}.",
        ) from exc
    if not result.is_finite() or result < 0:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Invalid shipping configuration: {field_name}.",
        )
    return result


def calculate_settings_shipping(
    *,
    subtotal: Decimal,
    shipping_enabled: Any,
    threshold: Any,
    flat_rate: Any,
) -> Decimal:
    """Return authoritative settings-driven shipping for customer checkout."""
    if not subtotal.is_finite() or subtotal < 0:
        raise HTTPException(status_code=422, detail="Invalid cart subtotal.")

    if isinstance(shipping_enabled, bool):
        enabled = shipping_enabled
    else:
        normalized = str(shipping_enabled).strip().lower().replace("'", "").replace('"', "")
        if normalized not in {"true", "false"}:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Invalid shipping configuration: shipping_enabled.",
            )
        enabled = normalized == "true"

    if not enabled:
        return Decimal("0.00")

    threshold_decimal = _decimal(threshold, "free_shipping_threshold")
    flat_decimal = _decimal(flat_rate, "flat_shipping_rate")
    return Decimal("0.00") if subtotal >= threshold_decimal else flat_decimal.quantize(Decimal("0.01"))
