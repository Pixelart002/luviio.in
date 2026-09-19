"""HSN/GST lookup client.

The catalog never hardcodes GST slabs. Provider data is used for admin
suggestions and, when enabled, product financial-field validation.
"""
from __future__ import annotations

from typing import Any

import httpx

from app.core.config import settings


class TaxonomyProviderError(RuntimeError):
    pass


class HsnGstClient:
    async def _request(self, params: dict[str, Any]) -> dict[str, Any]:
        base = settings.TAXONOMY_API_BASE_URL.rstrip("/")
        if not base:
            raise TaxonomyProviderError("HSN/GST taxonomy provider is not configured")
        headers = {"Accept": "application/json"}
        if settings.TAXONOMY_API_KEY:
            headers["Authorization"] = f"Bearer {settings.TAXONOMY_API_KEY}"
        url = f"{base}/api/lookup"
        try:
            async with httpx.AsyncClient(timeout=settings.TAXONOMY_API_TIMEOUT_SECONDS) as client:
                response = await client.get(url, params=params, headers=headers)
                response.raise_for_status()
                payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise TaxonomyProviderError("HSN/GST taxonomy provider request failed") from exc
        if not isinstance(payload, dict):
            raise TaxonomyProviderError("HSN/GST taxonomy provider returned an invalid response")
        return payload

    async def search(self, query: str, limit: int = 8) -> list[dict[str, Any]]:
        payload = await self._request({"q": query.strip(), "limit": max(1, min(limit, 20))})
        matches = payload.get("matches") or payload.get("results") or []
        if not isinstance(matches, list):
            raise TaxonomyProviderError("HSN/GST taxonomy provider returned invalid matches")
        return [item for item in matches if isinstance(item, dict)]

    async def lookup(self, code: str) -> list[dict[str, Any]]:
        payload = await self._request({"code": code.strip()})
        results = payload.get("results") or payload.get("matches") or []
        if not isinstance(results, list):
            raise TaxonomyProviderError("HSN/GST taxonomy provider returned invalid results")
        return [item for item in results if isinstance(item, dict)]

    async def validate_product_tax(self, hsn_code: str, gst_percentage: int) -> dict[str, Any]:
        results = await self.lookup(hsn_code)
        if not results:
            raise TaxonomyProviderError(f"HSN code {hsn_code} was not found by the configured provider")
        rates: set[int] = set()
        for item in results:
            raw = item.get("gst_rate")
            if isinstance(raw, (int, float)):
                value = float(raw)
                if 0 <= value <= 100 and value.is_integer():
                    rates.add(int(value))
            elif isinstance(raw, str):
                for token in raw.replace("%", "").replace(",", "/").split("/"):
                    try:
                        value = float(token.strip())
                        if 0 <= value <= 100 and value.is_integer():
                            rates.add(int(value))
                    except ValueError:
                        continue
        if not rates:
            raise TaxonomyProviderError(f"HSN code {hsn_code} returned no usable GST rate from the configured provider")
        if gst_percentage not in rates:
            raise TaxonomyProviderError(
                f"GST {gst_percentage}% does not match provider data for HSN {hsn_code}; available rates: {sorted(rates)}"
            )
        return {"hsn_code": hsn_code, "gst_percentage": gst_percentage, "provider_results": results}


hsn_gst_client = HsnGstClient()
