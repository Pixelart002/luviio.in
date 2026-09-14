"""Inventory Router — canonical HTTP boundary."""
import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, Request, status

from app.core.dependencies import require_permission
from app.domains.inventory.service import InventoryService
from app.domains.inventory.schemas import StockAdjustmentRequest
from app.utils.response import success_response

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/inventory", tags=["Inventory"])


@router.get("/stock/{product_id}", status_code=status.HTTP_200_OK)
async def get_stock_level(request: Request, product_id: str) -> Dict[str, Any]:
    if hasattr(request.state, "actions"):
        request.state.actions.append(f"Fetching stock level for product: {product_id[:8]}...")
    result = await InventoryService().get_stock_level(product_id)
    if not result:
        return success_response(message="Product not found", data=None)
    return success_response(data=result.model_dump())


@router.post("/admin/adjust", status_code=status.HTTP_200_OK, dependencies=[Depends(require_permission("inventory:adjust"))])
async def adjust_stock(request: Request, payload: StockAdjustmentRequest) -> Dict[str, Any]:
    """Atomically adjust product stock and write a stock-audit record."""
    if hasattr(request.state, "actions"):
        request.state.actions.append(f"Admin stock adjustment for product: {payload.product_id[:8]}...")
    result = await InventoryService().repo.admin_adjust_stock(payload.product_id, payload.delta, payload.reason)
    return success_response(data=result, message="Stock adjusted successfully.")


@router.get("/availability/{product_id}", status_code=status.HTTP_200_OK)
async def check_availability(request: Request, product_id: str, quantity: int = 1) -> Dict[str, Any]:
    if hasattr(request.state, "actions"):
        request.state.actions.append(f"Checking availability for product: {product_id[:8]}... (qty: {quantity})")
    result = await InventoryService().check_availability(product_id, quantity)
    return success_response(data=result.model_dump())


@router.get("/low-stock", status_code=status.HTTP_200_OK)
async def get_low_stock_alerts(request: Request) -> Dict[str, Any]:
    if hasattr(request.state, "actions"):
        request.state.actions.append("Fetching low-stock products")
    alerts = await InventoryService().repo.get_low_stock_products()
    return success_response(data=alerts)


@router.post("/low-stock/scan", status_code=status.HTTP_200_OK)
async def trigger_low_stock_scan(request: Request) -> Dict[str, Any]:
    if hasattr(request.state, "actions"):
        request.state.actions.append("Triggering low-stock scan and publishing alerts")
    count = await InventoryService().check_and_publish_low_stock_alerts()
    return success_response(data={"alerts_published": count})


@router.post("/stale-orders/release", status_code=status.HTTP_200_OK)
async def release_stale_orders(request: Request, minutes_old: int = 30) -> Dict[str, Any]:
    if hasattr(request.state, "actions"):
        request.state.actions.append(f"Releasing stale pending orders older than {minutes_old} minutes")
    count = await InventoryService().release_stale_pending_orders(minutes_old)
    return success_response(data={"orders_released": count})
