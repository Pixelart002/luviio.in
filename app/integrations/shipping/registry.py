"""Shipping provider registry.

External courier integrations are intentionally disabled. Luviio currently
uses manual shipping fulfillment.
"""
from __future__ import annotations

from fastapi import HTTPException, status


def get_shipping_provider(key: str = "manual"):
    normalized = (key or "manual").strip().lower()
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=f"External shipping provider '{normalized}' is disabled. Shipping is handled manually.",
    )
