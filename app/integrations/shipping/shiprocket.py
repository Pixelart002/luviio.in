"""Shiprocket API adapter."""
from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any

import httpx

from app.integrations.shipping.base import ShippingProvider

logger = logging.getLogger(__name__)


class ShiprocketProvider(ShippingProvider):
    key = "shiprocket"
    # Production and Sandbox use different API hosts in the Shiprocket sandbox
    # console. Keep the URLs explicit so sandbox traffic can never hit production.
    documented_base_url = "https://apiv2.shiprocket.in/v1/external"

    def __init__(self) -> None:
        # Luviio is currently testing Shiprocket in sandbox. Production must
        # be explicitly selected with SHIPROCKET_ENV=production.
        self.environment = os.getenv("SHIPROCKET_ENV", "sandbox").strip().lower()
        if self.environment == "test":
            # Backward-compatible alias for older deployments; keep the log label explicit.
            self.environment = "sandbox"
        if self.environment not in {"sandbox", "production"}:
            raise RuntimeError("SHIPROCKET_ENV must be 'sandbox' (or legacy 'test') or 'production'.")
        # Sandbox is intentionally supported even when Luviio itself runs with
        # APP_ENV=production. SHIPROCKET_ENV is the source of truth; never
        # silently rewrite sandbox traffic to production.
        if self.environment == "sandbox":
            self.email = os.getenv("SHIPROCKET_EMAIL", "").strip()
            self.password = os.getenv("SHIPROCKET_PASSWORD", "").strip()
        else:
            self.email = os.getenv("SHIPROCKET_EMAIL", "").strip()
            self.password = os.getenv("SHIPROCKET_PASSWORD", "").strip()

        # Shiprocket sandbox uses the sandbox API hosts already configured for
        # Luviio's integration. Keep sandbox and production selection explicit.
        # These sandbox hosts are intentionally overridable because Shiprocket
        # may issue environment-specific endpoints to an account.
        self.sandbox_base_url = os.getenv(
            "SHIPROCKET_SANDBOX_BASE_URL",
            "https://api-sandbox.shiprocket.in/v1/external",
        ).strip().rstrip("/")
        self.sandbox_serviceability_base_url = os.getenv(
            "SHIPROCKET_SANDBOX_SERVICEABILITY_BASE_URL",
            "https://serviceability-sandbox.shiprocket.in",
        ).strip().rstrip("/")

        if self.environment == "sandbox":
            self.base_url = os.getenv(
                "SHIPROCKET_SANDBOX_BASE_URL",
                os.getenv("SHIPROCKET_BASE_URL", self.sandbox_base_url),
            ).strip().rstrip("/")
            self.serviceability_base_url = os.getenv(
                "SHIPROCKET_SANDBOX_SERVICEABILITY_BASE_URL",
                os.getenv("SHIPROCKET_SERVICEABILITY_BASE_URL", self.sandbox_serviceability_base_url),
            ).strip().rstrip("/")
        else:
            self.base_url = os.getenv(
                "SHIPROCKET_PRODUCTION_BASE_URL",
                os.getenv("SHIPROCKET_BASE_URL", self.documented_base_url),
            ).strip().rstrip("/")
            # Shiprocket's current documented production serviceability
            # endpoint is on the same apiv2 host as authentication and the
            # other external APIs. Do not honor a separate production
            # serviceability host: a stale/misconfigured override can make
            # authentication succeed while courier rates time out.
            self.serviceability_base_url = self.base_url
        self._token: str | None = None
        self._token_expires_at = 0.0
        self._token_refresh_margin_seconds = max(
            300,
            int(os.getenv("SHIPROCKET_TOKEN_REFRESH_MARGIN_SECONDS", "900")),
        )
        self._lock = asyncio.Lock()
        self._auth_timeout = httpx.Timeout(
            float(os.getenv("SHIPROCKET_AUTH_TIMEOUT_SECONDS", "4.0")),
            connect=float(os.getenv("SHIPROCKET_CONNECT_TIMEOUT_SECONDS", "2.0")),
            read=float(os.getenv("SHIPROCKET_AUTH_READ_TIMEOUT_SECONDS", "4.0")),
            write=float(os.getenv("SHIPROCKET_WRITE_TIMEOUT_SECONDS", "4.0")),
            pool=float(os.getenv("SHIPROCKET_POOL_TIMEOUT_SECONDS", "1.0")),
        )
        self._request_timeout = httpx.Timeout(
            float(os.getenv("SHIPROCKET_REQUEST_TIMEOUT_SECONDS", "4.0")),
            connect=float(os.getenv("SHIPROCKET_CONNECT_TIMEOUT_SECONDS", "2.0")),
            read=float(os.getenv("SHIPROCKET_READ_TIMEOUT_SECONDS", "4.0")),
            write=float(os.getenv("SHIPROCKET_WRITE_TIMEOUT_SECONDS", "4.0")),
            pool=float(os.getenv("SHIPROCKET_POOL_TIMEOUT_SECONDS", "1.0")),
        )

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
            auth_url = f"{self.base_url}/auth/login"
            try:
                async with httpx.AsyncClient(timeout=self._auth_timeout) as client:
                    response = await client.post(
                        auth_url,
                        json={"email": self.email, "password": self.password},
                    )
            except (httpx.ConnectTimeout, httpx.ConnectError, httpx.ReadTimeout, httpx.PoolTimeout) as exc:
                # Never log credentials/tokens. Log only the configured host so
                # Koyeb can distinguish a bad sandbox endpoint from bad creds.
                logger.error(
                    "[SHIPROCKET] Authentication connection failed | env=%s host=%s error_type=%s",
                    self.environment,
                    self.base_url,
                    type(exc).__name__,
                )
                raise RuntimeError(
                    f"Shiprocket authentication endpoint is unreachable ({type(exc).__name__})."
                ) from exc

            if response.is_error:
                # Safe diagnostic only: never log credentials or tokens.
                logger.error(
                    "[SHIPROCKET] Authentication failed | env=%s status=%s host=%s body=%s",
                    self.environment,
                    response.status_code,
                    self.base_url,
                    response.text[:500].replace("\n", " "),
                )
                response.raise_for_status()
            data = response.json()
            token = str(data.get("token") or "").strip()
            if not token:
                raise RuntimeError("Shiprocket authentication returned no token.")
            self._token = token
            self._token_expires_at = time.time() + (240 * 60 * 60) - self._token_refresh_margin_seconds
            return token

    async def _request(self, method: str, path: str, *, base_url: str | None = None, **kwargs: Any) -> dict[str, Any]:
        token = await self._token_value()
        request_base_url = (base_url or self.base_url).rstrip("/")
        headers = dict(kwargs.pop("headers", {}) or {})
        headers["Authorization"] = f"Bearer {token}"
        headers["Content-Type"] = "application/json"
        async with httpx.AsyncClient(timeout=self._request_timeout) as client:
            try:
                response = await client.request(
                    method,
                    f"{request_base_url}{path}",
                    headers=headers,
                    **kwargs,
                )
            except (httpx.ConnectTimeout, httpx.ConnectError, httpx.ReadTimeout, httpx.PoolTimeout) as exc:
                logger.warning(
                    "[SHIPROCKET] provider request connection failed | env=%s host=%s method=%s path=%s error_type=%s",
                    self.environment,
                    request_base_url,
                    method,
                    path,
                    type(exc).__name__,
                )
                raise RuntimeError(
                    f"Shiprocket request failed ({type(exc).__name__})."
                ) from exc

            if response.status_code == 401:
                self._token = None
                self._token_expires_at = 0
                token = await self._token_value()
                headers["Authorization"] = f"Bearer {token}"
                try:
                    response = await client.request(
                        method,
                        f"{request_base_url}{path}",
                        headers=headers,
                        **kwargs,
                    )
                except (httpx.ConnectTimeout, httpx.ConnectError, httpx.ReadTimeout, httpx.PoolTimeout) as exc:
                    logger.warning(
                        "[SHIPROCKET] provider retry connection failed | env=%s host=%s method=%s path=%s error_type=%s",
                        self.environment,
                        request_base_url,
                        method,
                        path,
                        type(exc).__name__,
                    )
                    raise RuntimeError(
                        f"Shiprocket request failed ({type(exc).__name__})."
                    ) from exc
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
        # Sandbox and production expose the same logical operation but the
        # sandbox serviceability host uses the non-trailing-slash path.
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

    async def list_pickup_locations(self) -> list[dict[str, Any]]:
        """Return pickup locations registered on the authenticated Shiprocket account.

        Shiprocket returns them under data.shipping_address. Keep parsing strict so
        an unexpected provider response cannot silently look like "no pickup".
        """
        response = await self._request("GET", "/settings/company/pickup")
        if not isinstance(response, dict):
            raise RuntimeError("Shiprocket pickup API returned an invalid response.")
        data = response.get("data")
        if not isinstance(data, dict):
            raise RuntimeError("Shiprocket pickup API returned no data object.")
        locations = data.get("shipping_address")
        if locations is None:
            raise RuntimeError("Shiprocket pickup API response is missing shipping_address.")
        if not isinstance(locations, list):
            raise RuntimeError("Shiprocket pickup API returned invalid shipping_address.")
        return [item for item in locations if isinstance(item, dict)]

    async def add_pickup_location(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Register a seller pickup location on the authenticated Shiprocket account."""
        required = (
            "pickup_location", "name", "email", "phone",
            "address", "city", "state", "country", "pin_code",
        )
        missing = [key for key in required if not str(payload.get(key) or "").strip()]
        if missing:
            raise ValueError(
                "Shiprocket pickup configuration is incomplete: "
                + ", ".join(missing)
            )
        return await self._request(
            "POST",
            "/settings/company/addpickup",
            json=payload,
        )

    async def create_shipment(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self._request("POST", "/orders/create/adhoc", json=payload)

    async def assign_awb(self, *, shipment_id: str, courier_id: int | None = None) -> dict[str, Any]:
        body: dict[str, Any] = {"shipment_id": int(shipment_id)}
        if courier_id is not None:
            body["courier_id"] = int(courier_id)
        return await self._request("POST", "/courier/assign/awb", json=body)

    async def generate_pickup(self, *, shipment_id: str, tracking_number: str | None = None) -> dict[str, Any]:
        return await self._request("POST", "/courier/generate/pickup", json={"shipment_id": [int(shipment_id)]})

    async def generate_label(self, *, shipment_id: str) -> dict[str, Any]:
        return await self._request("POST", "/courier/generate/label", json={"shipment_id": [int(shipment_id)]})

    async def generate_manifest(self, *, shipment_id: str) -> dict[str, Any]:
        return await self._request("POST", "/manifests/generate", json={"shipment_id": [int(shipment_id)]})

    async def print_manifest(self, *, order_id: str) -> dict[str, Any]:
        return await self._request("POST", "/manifests/print", json={"order_ids": [int(order_id)]})

    async def print_invoice(self, *, order_id: str) -> dict[str, Any]:
        return await self._request("POST", "/orders/print/invoice", json={"ids": [int(order_id)]})

    async def track(self, tracking_number: str) -> dict[str, Any]:
        return await self._request("GET", f"/courier/track/awb/{tracking_number}")

    async def cancel_shipment(
        self,
        *,
        shipment_id: str,
        tracking_number: str | None = None,
        order_id: str | None = None,
    ) -> dict[str, Any]:
        # Shiprocket has two distinct cancellation APIs:
        # - an already-AWB'd shipment is cancelled by AWB;
        # - a created order without an AWB is cancelled by Shiprocket order ID.
        # Never send Luviio's internal shipment UUID or Shiprocket shipment ID
        # to /orders/cancel/shipment/awbs; that endpoint expects AWBs.
        awb = str(tracking_number or "").strip()
        if awb:
            return await self._request(
                "POST",
                "/orders/cancel/shipment/awbs",
                json={"awbs": [awb]},
            )

        raw_order_id = str(order_id or "").strip()
        if raw_order_id:
            try:
                provider_order_id = int(raw_order_id)
            except (TypeError, ValueError) as exc:
                raise ValueError("Shiprocket order ID is invalid for cancellation.") from exc
            return await self._request(
                "POST",
                "/orders/cancel",
                json={"ids": [provider_order_id]},
            )

        raise ValueError("A Shiprocket AWB or provider order ID is required for cancellation.")
