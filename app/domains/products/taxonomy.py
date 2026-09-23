from __future__ import annotations

from typing import Any
from fastapi import HTTPException, status
from app.constants.product_messages import ProductRules, ProductSecurityMessages

def gst_rates(_results: list[dict[str, Any]] | None = None) -> list[int]:
    return list(ProductRules.LEGAL_GST_SLABS)

async def search_hsn(query: str, limit: int = 8) -> list[dict[str, Any]]:
    raise HTTPException(status_code=status.HTTP_410_GONE, detail="HSN lookup has been removed. Enter the 4-8 digit HSN code manually.")

async def lookup_hsn(code: str) -> list[dict[str, Any]]:
    value = str(code or "").strip()
    if not value.isdigit() or not 4 <= len(value) <= 8:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="HSN code must contain 4-8 digits.")
    raise HTTPException(status_code=status.HTTP_410_GONE, detail="HSN lookup has been removed. Enter the HSN code manually.")

async def validate_product_tax(hsn_code: str, gst_percentage: int) -> None:
    code = str(hsn_code or "").strip()
    if not code.isdigit() or not 4 <= len(code) <= 8:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="HSN code must contain 4-8 digits.")
    if gst_percentage not in ProductRules.LEGAL_GST_SLABS:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=ProductSecurityMessages.INVALID_GST_SLAB)
