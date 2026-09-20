"""Shiprocket API adapter."""
from __future__ import annotations
import asyncio, os, time
from typing import Any
import httpx
from app.integrations.shipping.base import ShippingProvider
from app.core.config import settings
import logging

class ShiprocketProvider(ShippingProvider):
    key = "shiprocket"
    # Production and Sandbox use different API hosts in the Shiprocket sandbox
    # console. Keep the URLs explicit so sandbox traffic can never hit production.
    production_base_url = "https://apiv2.shiprocket.in/v1/external"
    sandbox_base_url = "https://api-sandbox.shiprocket.in/v1/external"
    sandbox_serviceability_url = "https://serviceability-sandbox.shiprocket.in"

    def __init__(self) -> None:
        self.environment = os.getenv("SHIPROCKET_ENV", "production").strip().lower()
        if self.environment == "test":
            # Backward-compatible alias for older deployments; keep the log label explicit.
            self.environment = "sandbox"
        if self.environment not in {"sandbox", "production"}:
            raise RuntimeError("SHIPROCKET_ENV must be 'sandbox' (or legacy 'test') or 'production'.")
        # Production must never silently use the sandbox host. If an old
        # deployment still has SHIPROCKET_ENV=sandbox, force the provider back
        # to production unless sandbox has been explicitly allowed.
        allow_sandbox = os.getenv("SHIPROCKET_ALLOW_SANDBOX", "false").strip().lower() == "true"
        if settings.APP_ENV == "production" and self.environment == "sandbox" and not allow_sandbox:
            logging.getLogger(__name__).warning(
                "[SHIPROCKET] Ignoring sandbox environment in production; forcing production API hosts."
            )
            self.environment = "production"

        if self.environment == "sandbox":
            self.email = os.getenv("SHIPROCKET_EMAIL", "").strip()
            self.password = os.getenv("SHIPROCKET_PASSWORD", "").strip()
        else:
            self.email = os.getenv("SHIPROCKET_EMAIL", "").strip()
            self.password = os.getenv("SHIPROCKET_PASSWORD", "").strip()

        # Explicit override is useful for provider-issued environments. For
        # sandbox, default to Shiprocket's sandbox hosts shown by the sandbox API
        # console: api-sandbox for auth/order APIs and the dedicated
        # serviceability-sandbox host for courier serviceability.
        if self.environment == "sandbox":
            self.base_url = os.getenv("SHIPROCKET_BASE_URL", self.sandbox_base_url).strip().rstrip("/")
            self.serviceability_base_url = os.getenv(
                "SHIPROCKET_SERVICEABILITY_BASE_URL",
                self.sandbox_serviceability_url,
            ).strip().rstrip("/")
        else:
            self.base_url = os.getenv("SHIPROCKET_BASE_URL", self.production_base_url).strip().rstrip("/")
            self.serviceability_base_url = os.getenv(
                "SHIPROCKET_SERVICEABILITY_BASE_URL",
                self.base_url,
            ).strip().rstrip("/")
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
                if response.is_error:
                    # Safe diagnostic only: never log credentials or tokens.
                    import logging
                    logging.getLogger(__name__).error(
                        "[SHIPROCKET] Authentication failed | env=%s status=%s body=%s",
                        self.environment,
                        response.status_code,
                        response.text[:500].replace("\n", " "),
                    )
                    response.raise_for_status()
                data = response.json()
            token = str(data.get("token") or "").strip()
            if not token:
                raise RuntimeError("Shiprocket authentication returned no token.")
            self._token = token
            self._token_expires_at = time.time() + (240 * 60 * 60) - 300
            return token

    async def _request(self, method: str, path: str, *, base_url: str | None = None, **kwargs: Any) -> dict[str, Any]:
        token = await self._token_value()
        request_base_url = (base_url or self.base_url).rstrip("/")
        headers = dict(kwargs.pop("headers", {}) or {})
        headers["Authorization"] = f"Bearer {token}"
        headers["Content-Type"] = "application/json"
        async with httpx.AsyncClient(timeout=httpx.Timeout(20.0, connect=5.0)) as client:
            response = await client.request(method, f"{request_base_url}{path}", headers=headers, **kwargs)
            if response.status_code == 401:
                self._token = None
                self._token_expires_at = 0
                token = await self._token_value()
                headers["Authorization"] = f"Bearer {token}"
                response = await client.request(method, f"{request_base_url}{path}", headers=headers, **kwargs)
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError:
                logging.getLogger(__name__).error(
                    "[SHIPROCKET] API request failed | env=%s status=%s method=%s path=%s body=%s",
                    self.environment,
                    response.status_code,
                    method,
                    path,
                    response.text[:2000].replace("\n", " "),
                )
                raise
            data = response.json()
            return data if isinstance(data, dict) else {"data": data}

    async def serviceability(self, *, pickup_postcode: str, delivery_postcode: str, weight_kg: float, cod: bool, declared_value: float | None = None) -> dict[str, Any]:
        params: dict[str, Any] = {
            "pickup_postcode": pickup_postcode, "delivery_postcode": delivery_postcode,
            "weight": weight_kg, "cod": 1 if cod else 0,
        }
        if declared_value is not None:
            params["declared_value"] = declared_value
        # Shiprocket documents the production endpoint with a trailing slash.
        # The sandbox serviceability host currently canonicalizes the opposite
        # way (trailing slash -> no slash), so keep the two endpoint forms explicit.
        serviceability_path = (
            "/courier/serviceability"
            if self.environment == "sandbox"
            else "/courier/serviceability/"
        )
        return await self._request(
            "GET",
            serviceability_path,
            params=params,
            base_url=self.serviceability_base_url,
        )

    async def create_shipment(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self._request("POST", "/orders/create/adhoc", json=payload)

    async def assign_awb(self, *, shipment_id: str, courier_id: int | None = None) -> dict[str, Any]:
        body: dict[str, Any] = {"shipment_id": int(shipment_id)}
        if courier_id is not None:
            body["courier_id"] = int(courier_id)
        return await self._request("POST", "/courier/assign/awb", json=body)

    async def generate_pickup(self, *, shipment_id: str) -> dict[str, Any]:
        return await self._request("POST", "/courier/generate/pickup", json={"shipment_id": [int(shipment_id)]})

    async def generate_label(self, *, shipment_id: str) -> dict[str, Any]:
        return await self._request("POST", "/courier/generate/label", json={"shipment_id": [int(shipment_id)]})

    async def generate_manifest(self, *, shipment_id: str) -> dict[str, Any]:
        return await self._request("POST", "/manifests/generate", json={"shipment_id": [int(shipment_id)]})

    async def print_invoice(self, *, shipment_id: str) -> dict[str, Any]:
        return await self._request("POST", "/orders/print/invoice", json={"ids": [int(shipment_id)]})

    async def track(self, tracking_number: str) -> dict[str, Any]:
        return await self._request("GET", f"/courier/track/awb/{tracking_number}")

    async def cancel_shipment(self, shipment_id: str) -> dict[str, Any]:
        return await self._request("POST", "/orders/cancel", json={"ids": [int(shipment_id)]})
