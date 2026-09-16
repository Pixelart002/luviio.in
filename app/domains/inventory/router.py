"""Inventory Router — canonical HTTP boundary."""
import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, Query, Request, status

from app.core.dependencies import require_permission
from app.domains.inventory.schemas import (
    InventoryOperationRequest,
    InventoryReconcileRequest,
    StockAdjustmentRequest,
)
from app.domains.inventory.service import InventoryService
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
    if hasattr(request.state, "actions"):
        request.state.actions.append(f"Admin stock adjustment for product: {payload.product_id[:8]}...")
    result = await InventoryService().adjust_stock(payload.product_id, payload.delta, payload.reason)
    return success_response(data=result, message="Stock adjusted successfully.")


@router.post("/admin/receive", status_code=status.HTTP_200_OK, dependencies=[Depends(require_permission("inventory:receive"))])
async def receive_stock(request: Request, payload: InventoryOperationRequest) -> Dict[str, Any]:
    if hasattr(request.state, "actions"):
        request.state.actions.append(f"Receiving stock for product: {payload.product_id[:8]}...")
    result = await InventoryService().receive_stock(payload)
    return success_response(data=result.model_dump(), message="Stock received successfully.")


@router.post("/admin/return", status_code=status.HTTP_200_OK, dependencies=[Depends(require_permission("inventory:return"))])
async def record_return(request: Request, payload: InventoryOperationRequest) -> Dict[str, Any]:
    result = await InventoryService().record_return(payload)
    return success_response(data=result.model_dump(), message="Return stock recorded successfully.")


@router.post("/admin/damage", status_code=status.HTTP_200_OK, dependencies=[Depends(require_permission("inventory:damage"))])
async def record_damage(request: Request, payload: InventoryOperationRequest) -> Dict[str, Any]:
    result = await InventoryService().record_damage(payload)
    return success_response(data=result.model_dump(), message="Damaged stock recorded successfully.")


@router.post("/admin/wastage", status_code=status.HTTP_200_OK, dependencies=[Depends(require_permission("inventory:wastage"))])
async def record_wastage(request: Request, payload: InventoryOperationRequest) -> Dict[str, Any]:
    result = await InventoryService().record_wastage(payload)
    return success_response(data=result.model_dump(), message="Wastage recorded successfully.")


@router.post("/admin/reconcile", status_code=status.HTTP_200_OK, dependencies=[Depends(require_permission("inventory:reconcile"))])
async def reconcile_stock(request: Request, payload: InventoryReconcileRequest) -> Dict[str, Any]:
    result = await InventoryService().reconcile_stock(payload)
    return success_response(data=result.model_dump(), message="Stock reconciliation completed.")


@router.get("/admin/summary", status_code=status.HTTP_200_OK, dependencies=[Depends(require_permission("inventory:read"))])
async def inventory_summary(request: Request, low_stock_only: bool = Query(False)) -> Dict[str, Any]:
    data = await InventoryService().get_summary(low_stock_only=low_stock_only)
    return success_response(data=data)


@router.get("/admin/history/{product_id}", status_code=status.HTTP_200_OK, dependencies=[Depends(require_permission("inventory:history:read"))])
async def inventory_history(
    request: Request,
    product_id: str,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> Dict[str, Any]:
    data = await InventoryService().list_history(product_id, limit=limit, offset=offset)
    return success_response(data=data)


@router.get("/availability/{product_id}", status_code=status.HTTP_200_OK)
async def check_availability(request: Request, product_id: str, quantity: int = Query(1, ge=1, le=1000000)) -> Dict[str, Any]:
    if hasattr(request.state, "actions"):
        request.state.actions.append(f"Checking availability for product: {product_id[:8]}... (qty: {quantity})")
    result = await InventoryService().check_availability(product_id, quantity)
    return success_response(data=result.model_dump())


@router.get("/low-stock", status_code=status.HTTP_200_OK, dependencies=[Depends(require_permission("inventory:low_stock:read"))])
async def get_low_stock_alerts(request: Request) -> Dict[str, Any]:
    if hasattr(request.state, "actions"):
        request.state.actions.append("Fetching low-stock products")
    alerts = await InventoryService().repo.get_low_stock_products()
    return success_response(data=alerts)


@router.post("/low-stock/scan", status_code=status.HTTP_200_OK, dependencies=[Depends(require_permission("inventory:low_stock:read"))])
async def trigger_low_stock_scan(request: Request) -> Dict[str, Any]:
    if hasattr(request.state, "actions"):
        request.state.actions.append("Triggering low-stock scan and publishing alerts")
    count = await InventoryService().check_and_publish_low_stock_alerts()
    return success_response(data={"alerts_published": count})


@router.post("/stale-orders/release", status_code=status.HTTP_200_OK, dependencies=[Depends(require_permission("inventory:reservation:release"))])
async def release_stale_orders(request: Request, minutes_old: int = Query(30, ge=1, le=1440)) -> Dict[str, Any]:
    if hasattr(request.state, "actions"):
        request.state.actions.append(f"Releasing stale pending orders older than {minutes_old} minutes")
    count = await InventoryService().release_stale_pending_orders(minutes_old)
    return success_response(data={"orders_released": count})
