from __future__ import annotations

from typing import Any
from fastapi import HTTPException, status
from app.constants.product_messages import ProductRules, ProductSecurityMessages

def gst_rates(_results: list[dict[str, Any]] | None = None) -> list[int]:
    return list(ProductRules.LEGAL_GST_SLABS)

async def validate_product_tax(hsn_code: str, gst_percentage: int) -> None:
    code = str(hsn_code or "").strip()
    if not code.isdigit() or not 4 <= len(code) <= 8:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="HSN code must contain 4-8 digits.")
    if gst_percentage not in ProductRules.LEGAL_GST_SLABS:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=ProductSecurityMessages.INVALID_GST_SLAB)
