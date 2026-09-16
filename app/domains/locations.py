"""Location discovery integration backed by Ola Maps.

The API key stays server-side. This module normalizes Ola responses so the
frontend is insulated from provider response-shape changes.
"""
import logging
from typing import Any
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.config import settings
from app.core.dependencies import get_current_user
from app.utils.response import success_response

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/locations", tags=["Locations"])
limiter = Limiter(key_func=get_remote_address)
OLA_BASE_URL = "https://api.olamaps.io"


def _extract_items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("predictions", "suggestions", "places", "results", "items"):
        value = payload.get(key)
        if isinstance(value, list):
            return [x for x in value if isinstance(x, dict)]
    data = payload.get("data")
    if isinstance(data, (dict, list)):
        return _extract_items(data)
    return []


def _first(item: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = item.get(key)
        if value not in (None, ""):
            return value
    return None


def _normalize_suggestion(item: dict[str, Any]) -> dict[str, Any]:
    location = item.get("location") or item.get("geometry") or {}
    if isinstance(location, dict) and isinstance(location.get("location"), dict):
        location = location["location"]
    return {
        "place_id": str(_first(item, "place_id", "placeId", "id") or ""),
        "name": str(_first(item, "name", "description") or ""),
        "address": str(_first(item, "address", "formatted_address", "formattedAddress", "description") or ""),
        "latitude": _first(location, "lat", "latitude") if isinstance(location, dict) else None,
        "longitude": _first(location, "lng", "lon", "longitude") if isinstance(location, dict) else None,
        "type": _first(item, "type", "category", "types"),
    }


def _normalize_details(payload: dict[str, Any]) -> dict[str, Any]:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    address = data.get("address") if isinstance(data.get("address"), dict) else {}
    components = data.get("address_components") or data.get("addressComponents") or []
    if not isinstance(components, list):
        components = []

    def component(*names: str) -> str:
        wanted = {name.lower() for name in names}
        for item in components:
            if not isinstance(item, dict):
                continue
            kinds = item.get("types") or item.get("type") or []
            if isinstance(kinds, str):
                kinds = [kinds]
            if any(str(kind).lower() in wanted for kind in kinds):
                return str(_first(item, "long_name", "longName", "name", "value") or "")
        for key in names:
            value = address.get(key) or data.get(key)
            if value:
                return str(value)
        return ""

    location = data.get("location") or data.get("geometry") or {}
    if isinstance(location, dict) and isinstance(location.get("location"), dict):
        location = location["location"]
    return {
        "place_id": str(_first(data, "place_id", "placeId", "id") or ""),
        "name": str(_first(data, "name", "title") or ""),
        "formatted_address": str(_first(data, "formatted_address", "formattedAddress", "address") or ""),
        "line1": component("street_number", "premise", "subpremise", "route", "street"),
        "city": component("locality", "city", "postal_town", "town", "village"),
        "district": component("administrative_area_level_2", "district", "county"),
        "state": component("administrative_area_level_1", "state"),
        "state_code": component("administrative_area_level_1_short", "state_code", "stateCode"),
        "postal_code": component("postal_code", "postcode", "pincode", "pin_code"),
        "country": component("country") or "India",
        "latitude": _first(location, "lat", "latitude") if isinstance(location, dict) else None,
        "longitude": _first(location, "lng", "lon", "longitude") if isinstance(location, dict) else None,
    }


async def _ola_get(path: str, params: dict[str, Any]) -> dict[str, Any]:
    if not settings.OLA_MAPS_API_KEY:
        raise RuntimeError("Ola Maps API is not configured on the server")

    query = {**params, "api_key": settings.OLA_MAPS_API_KEY}
    url = f"{OLA_BASE_URL}{path}?{urlencode(query)}"
    async with httpx.AsyncClient(timeout=httpx.Timeout(6.0, connect=3.0)) as client:
        response = await client.get(url)

    if response.status_code == 403:
        logger.error("Ola Maps authentication rejected | endpoint=%s status=403", path)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Location provider authentication is unavailable",
        )
    if response.status_code == 429:
        logger.warning("Ola Maps rate limit reached | endpoint=%s", path)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Location provider rate limit reached",
        )
    if response.is_error:
        logger.error("Ola Maps request failed | endpoint=%s status=%s", path, response.status_code)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Location provider is temporarily unavailable",
        )

    payload = response.json()
    return payload if isinstance(payload, dict) else {"data": payload}


@router.get("/autocomplete", status_code=status.HTTP_200_OK)
@limiter.limit("30/minute")
async def autocomplete(
    request: Request,
    input: str = Query(..., min_length=2, max_length=120),
    language: str = Query("en", pattern="^[a-z]{2}$"),
    _: dict[str, Any] = Depends(get_current_user),
):
    query = input.strip()
    if len(query) < 2:
        return success_response(data={"items": []}, message="Location suggestions")
    try:
        payload = await _ola_get("/places/v1/autocomplete", {"input": query, "language": language})
        items = [_normalize_suggestion(item) for item in _extract_items(payload)]
        return success_response(data={"items": items[:8]}, message="Location suggestions")
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Ola Maps autocomplete integration failed | type=%s", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Location search is temporarily unavailable",
        ) from exc


@router.get("/details", status_code=status.HTTP_200_OK)
@limiter.limit("30/minute")
async def details(
    request: Request,
    place_id: str = Query(..., min_length=1, max_length=200),
    language: str = Query("en", pattern="^[a-z]{2}$"),
    _: dict[str, Any] = Depends(get_current_user),
):
    try:
        payload = await _ola_get("/places/v1/details", {"place_id": place_id.strip(), "language": language})
        return success_response(data=_normalize_details(payload), message="Location details")
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Ola Maps place-details integration failed | type=%s", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Location details are temporarily unavailable",
        ) from exc
