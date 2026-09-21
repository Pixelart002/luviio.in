"""Provider-neutral shipping integration contract."""
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any

class ShippingProvider(ABC):
    key: str

    @abstractmethod
    async def serviceability(self, *, pickup_postcode: str, delivery_postcode: str, weight_kg: float, cod: bool, declared_value: float | None = None) -> dict[str, Any]: ...

    @abstractmethod
    async def create_shipment(self, payload: dict[str, Any]) -> dict[str, Any]: ...

    @abstractmethod
    async def assign_awb(self, *, shipment_id: str, courier_id: int | None = None) -> dict[str, Any]: ...

    @abstractmethod
    async def generate_pickup(self, *, shipment_id: str) -> dict[str, Any]: ...

    @abstractmethod
    async def generate_label(self, *, shipment_id: str) -> dict[str, Any]: ...

    @abstractmethod
    async def generate_manifest(self, *, shipment_id: str) -> dict[str, Any]: ...

    @abstractmethod
    async def print_invoice(self, *, order_id: str) -> dict[str, Any]: ...

    @abstractmethod
    async def track(self, tracking_number: str) -> dict[str, Any]: ...

    async def cancel_shipment(self, shipment_id: str) -> dict[str, Any]:
        raise NotImplementedError
