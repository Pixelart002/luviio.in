"""Product-domain tax taxonomy service."""
from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status

from app.core.config import settings
from app.integrations.taxonomy.client import TaxonomyProviderError, hsn_gst_client


async def search_hsn(query: str, limit: int = 8) -> list[dict[str, Any]]:
    if len(query.strip()) < 2:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="HSN search requires at least 2 characters.")
    try:
        return await hsn_gst_client.search(query, limit)
    except TaxonomyProviderError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


async def lookup_hsn(code: str) -> list[dict[str, Any]]:
    if not code.strip().isdigit() or not 4 <= len(code.strip()) <= 8:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="HSN code must contain 4-8 digits.")
    try:
        return await hsn_gst_client.lookup(code)
    except TaxonomyProviderError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


async def validate_product_tax(hsn_code: str, gst_percentage: int) -> None:
    if not settings.TAXONOMY_ENFORCE_PRODUCT_TAX:
        return
    try:
        await hsn_gst_client.validate_product_tax(hsn_code, gst_percentage)
    except TaxonomyProviderError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
