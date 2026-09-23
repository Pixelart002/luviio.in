"""GST Accelerator integration for admin-only HSN typeahead suggestions.

The provider is accessed server-side so its API key never reaches the browser.
This integration only suggests HSN codes; it never writes or auto-assigns product data.
"""
import os
from typing import Any

import httpx

BASE_URL = "https://gstaccelerator.in/api/v1"


class GSTAcceleratorError(RuntimeError):
    pass


def _api_key() -> str:
    key = os.getenv("GST_ACCELERATOR_API_KEY", "").strip()
    if not key:
        raise GSTAcceleratorError("GST_ACCELERATOR_API_KEY is not configured")
    return key


async def suggest_hsn(query: str) -> list[dict[str, Any]]:
    q = " ".join(query.split()).strip()
    if len(q) < 2:
        return []
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(4.0, connect=2.0)) as client:
            response = await client.get(
                f"{BASE_URL}/autocomplete",
                params={"q": q},
                headers={"X-API-Key": _api_key(), "Accept": "application/json"},
            )
        if response.status_code != 200:
            raise GSTAcceleratorError(f"provider returned HTTP {response.status_code}")
        payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise GSTAcceleratorError("provider request failed") from exc

    if not isinstance(payload, list):
        raise GSTAcceleratorError("provider returned an invalid response")

    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in payload[:10]:
        if not isinstance(row, dict):
            continue
        code = str(row.get("hsn_code") or "").strip()
        description = str(row.get("hsn_description") or row.get("description") or "").strip()
        if not code or not description or not code.isdigit() or not 4 <= len(code) <= 8 or code in seen:
            continue
        seen.add(code)
        items.append({"hsn_code": code, "description": description})
    return items
