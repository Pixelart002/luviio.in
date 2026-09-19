"""Shiprocket API adapter.

Credentials are read only from server-side environment variables:
SHIPROCKET_EMAIL and SHIPROCKET_PASSWORD.
"""
from __future__ import annotations

import asyncio
import os
import time
from typing import Any

import httpx

from app.integrations.shipping.base import ShippingProvider


class ShiprocketProvider(ShippingProvider):
    key = "shiprocket"
    base_url = "https://apiv2.shiprocket.in/v1/external"

    def __init__(self) -> None:
        self.email = os.getenv("SHIPROCKET_EMAIL", "").strip()
        self.password = os.getenv("SHIPROCKET_PASSWORD", "").strip()
        self._token: str | None = None
        self._token_expires_at = 0.0
        self._lock = asyncio.Lock()

    def _configured(self) -> None:
        if not self.email or not self.password:
            raise RuntimeError("Shiprocket provider is not configured.")

    async def _token_value(self) -> str:
        self._configured()
        if self._token and time.time() < self._token_expires_at:
            return self._token
        async with self._lock:
            if self._token and time.time() < self._token_expires_at:
                return self._token
            async with httpx.AsyncClient(timeout=httpx.Timeout(15.0, connect=5.0)) as client:
                response = await client.post(
                    f"{self.base_url}/auth/login",
                    json={"email": self.email, "password": self.password},
                )
                response.raise_for_status()
                data = response.json()
            token = str(data.get("token") or "").strip()
            if not token:
                raise RuntimeError("Shiprocket authentication returned no token.")
            self._token = token
            # Shiprocket documents a 240-hour token validity. Refresh earlier
            # so clock skew or provider-side rotation does not hit checkout.
            self._token_expires_at = time.time() + (9 * 24 * 60 * 60)
            return token

    async def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        token = await self._token_value()
        headers = dict(kwargs.pop("headers", {}) or {})
        headers["Authorization"] = f"Bearer {token}"
        headers["Content-Type"] = "application/json"
        async with httpx.AsyncClient(timeout=httpx.Timeout(20.0, connect=5.0)) as client:
            response = await client.request(method, f"{self.base_url}{path}", headers=headers, **kwargs)
            if response.status_code == 401:
                self._token = None
                self._token_expires_at = 0
                token = await self._token_value()
                headers["Authorization"] = f"Bearer {token}"
                response = await client.request(method, f"{self.base_url}{path}", headers=headers, **kwargs)
            response.raise_for_status()
            data = response.json()
            return data if isinstance(data, dict) else {"data": data}

    async def serviceability(self, *, pickup_postcode: str, delivery_postcode: str, weight_kg: float, cod: bool) -> dict[str, Any]:
        params = {
            "pickup_postcode": pickup_postcode,
            "delivery_postcode": delivery_postcode,
            "weight": weight_kg,
            "cod": 1 if cod else 0,
        }
        return await self._request("GET", "/courier/serviceability/", params=params)

    async def create_shipment(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self._request("POST", "/orders/create/adhoc", json=payload)

    async def track(self, tracking_number: str) -> dict[str, Any]:
        return await self._request("GET", f"/courier/track/awb/{tracking_number}")

    async def cancel_shipment(self, shipment_id: str) -> dict[str, Any]:
        return await self._request("POST", "/orders/cancel", json={"ids": [shipment_id]})
