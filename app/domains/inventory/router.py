"""
Inventory Router
================
Path: app/domains/inventory/router.py

HTTP endpoints for inventory management.
Thin layer — delegates all logic to InventoryService.
"""
import logging
from typing import Any, Dict
from fastapi import APIRouter, Depends, Request, status

from app.core.dependencies import require_permission
from app.domains.inventory.service import InventoryService
from app.domains.inventory.policy import InventoryPolicy
from app.utils.response import success_response

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/inventory", tags=["Inventory"])


@router.get("/stock/{product_id}", status_code=status.HTTP_200_OK)
async def get_stock_level(request: Request, product_id: str) -> Dict[str, Any]:
    """Get current stock level for a product."""
    if hasattr(request.state, "actions"):
        request.state.actions.append(f"Fetching stock level for product: {product_id[:8]}...")
    result = await InventoryService().get_stock_level(product_id)
    if not result:
        return success_response(message="Product not found", data=None)
    return success_response(data=result.model_dump())


@router.get("/availability/{product_id}", status_code=status.HTTP_200_OK)
async def check_availability(request: Request, product_id: str, quantity: int = 1) -> Dict[str, Any]:
    """Check if a product is available in the requested quantity."""
    if hasattr(request.state, "actions"):
        request.state.actions.append(f"Checking availability for product: {product_id[:8]}... (qty: {quantity})")
    result = await InventoryService().check_availability(product_id, quantity)
    return success_response(data=result.model_dump())


@router.get("/low-stock", status_code=status.HTTP_200_OK)
async def get_low_stock_alerts(request: Request) -> Dict[str, Any]:
    """Get products that are at or below their low-stock threshold."""
    if hasattr(request.state, "actions"):
        request.state.actions.append("Fetching low-stock products")
    service = InventoryService()
    alerts = await service.repo.get_low_stock_products()
    return success_response(data=alerts)


@router.post("/low-stock/scan", status_code=status.HTTP_200_OK)
async def trigger_low_stock_scan(request: Request) -> Dict[str, Any]:
    """Manually trigger a low-stock scan and publish alerts."""
    if hasattr(request.state, "actions"):
        request.state.actions.append("Triggering low-stock scan and publishing alerts")
    count = await InventoryService().check_and_publish_low_stock_alerts()
    return success_response(data={"alerts_published": count})


@router.post("/stale-orders/release", status_code=status.HTTP_200_OK)
async def release_stale_orders(request: Request, minutes_old: int = 30) -> Dict[str, Any]:
    """Release stock from stale pending orders (abandoned checkout cleanup)."""
    if hasattr(request.state, "actions"):
        request.state.actions.append(f"Releasing stale pending orders older than {minutes_old} minutes")
    count = await InventoryService().release_stale_pending_orders(minutes_old)
    return success_response(data={"orders_released": count})
