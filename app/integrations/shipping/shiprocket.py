from __future__ import annotations

import os
from typing import Any

import httpx
from fastapi import HTTPException, status


class ShiprocketClient:
    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self.base_url = os.getenv("SHIPROCKET_BASE_URL", "https://apiv2.shiprocket.in/v1/external").rstrip("/")
        self.email = os.getenv("SHIPROCKET_EMAIL", "")
        self.password = os.getenv("SHIPROCKET_PASSWORD", "")
        self._token: str | None = None
        self.client = client

    async def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        if not self.client:
            async with httpx.AsyncClient(timeout=httpx.Timeout(10.0, connect=3.0)) as client:
                return await self._send(client, method, path, **kwargs)
        return await self._send(self.client, method, path, **kwargs)

    async def _send(self, client: httpx.AsyncClient, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        if not self.email or not self.password:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Shiprocket is not configured")
        if not self._token:
            auth = await client.post(f"{self.base_url}/auth/login", json={"email": self.email, "password": self.password})
            auth.raise_for_status()
            self._token = auth.json().get("token")
            if not self._token:
                raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Shiprocket authentication failed")
        response = await client.request(method, f"{self.base_url}/{path.lstrip('/')}", headers={"Authorization": f"Bearer {self._token}"}, **kwargs)
        if response.status_code == 401:
            self._token = None
            auth = await client.post(f"{self.base_url}/auth/login", json={"email": self.email, "password": self.password})
            auth.raise_for_status()
            self._token = auth.json().get("token")
            if not self._token:
                raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Shiprocket authentication failed")
            response = await client.request(method, f"{self.base_url}/{path.lstrip('/')}", headers={"Authorization": f"Bearer {self._token}"}, **kwargs)
        response.raise_for_status()
        return response.json()

    async def check_serviceability(self, pickup_postcode: str, delivery_postcode: str, weight_kg: float, cod: bool) -> dict[str, Any]:
        return await self._request("GET", "/courier/serviceability", params={"pickup_postcode": pickup_postcode, "delivery_postcode": delivery_postcode, "weight": weight_kg, "cod": int(cod)})

    async def create_order(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self._request("POST", "/orders/create/adhoc", json=payload)

    async def cancel_order(self, ids: list[int]) -> dict[str, Any]:
        return await self._request("POST", "/orders/cancel", json={"ids": ids})

    async def track(self, shipment_id: str) -> dict[str, Any]:
        return await self._request("GET", f"/courier/track/shipment/{shipment_id}")
