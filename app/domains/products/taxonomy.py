"""Product-domain tax taxonomy service."""
from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status

from app.core.config import settings
from app.integrations.taxonomy.client import TaxonomyProviderError, hsn_gst_client


def _extract_gst_rates(results: list[dict[str, Any]]) -> list[int]:
    rates: set[int] = set()
    for item in results:
        raw = item.get("gst_rate")
        values = [raw] if isinstance(raw, (int, float, str)) else []
        for value in values:
            tokens = value.replace("%", "").replace(",", "/").split("/") if isinstance(value, str) else [value]
            for token in tokens:
                try:
                    number = float(str(token).strip())
                except (TypeError, ValueError):
                    continue
                if 0 <= number <= 100 and number.is_integer():
                    rates.add(int(number))
    return sorted(rates)


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


def gst_rates(results: list[dict[str, Any]]) -> list[int]:
    return _extract_gst_rates(results)


async def validate_product_tax(hsn_code: str, gst_percentage: int) -> None:
    if not settings.TAXONOMY_ENFORCE_PRODUCT_TAX:
        return
    try:
        await hsn_gst_client.validate_product_tax(hsn_code, gst_percentage)
    except TaxonomyProviderError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
