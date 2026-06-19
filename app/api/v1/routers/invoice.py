"""
Invoice Router — Async Enterprise Grade
=======================================
Path: app/api/v1/routers/invoice.py

Architecture Upgrades:
  1. ALL Supabase DB logic strictly asynchronous (await).
  2. PDF Generation offloaded to a threadpool to prevent blocking the event loop.
  3. 🔥 SECURITY FIX: ABAC Zero-IDOR guard `get_user_id_strict` injected.
"""
from __future__ import annotations

import io
import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from starlette.concurrency import run_in_threadpool

# 🔥 ARCHITECTURE IMPORTS: Added get_user_id_strict
from app.core.dependencies import get_current_user, get_user_id_strict
from app.repositories.order_repo import AsyncOrderRepository
from app.repositories.user_repo import AsyncUserRepository
from app.utils.documents.pdf_invoice import build_invoice_pdf

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/orders", tags=["Invoice"])

_INVOICEABLE = frozenset({"paid", "shipped", "delivered", "refunded"})

# ── Helpers ───────────────────────────────────────────────────────────────────

# 🔥 DEPRECATED: Replaced by get_user_id_strict Dependency natively in the route
# def _get_user_id(current: dict[str, Any]) -> str:
#     profile = current.get("profile", {})
#     user_id = profile.get("id") or current.get("id") or current.get("sub")
#     if not user_id: raise HTTPException(401, "User ID not found")
#     return str(user_id)

def _is_admin(current: dict[str, Any]) -> bool:
    return current.get("profile", {}).get("role") == "admin"

# ══════════════════════════════════════════════════════════════════════════════
#  INVOICE ENDPOINT
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/{order_id}/invoice")
async def download_invoice(
    request: Request,
    order_id: UUID,
    current: dict[str, Any] = Depends(get_current_user),
    user_id: str = Depends(get_user_id_strict) # 🔥 STRICT ABAC GUARD
) -> StreamingResponse:
    """
    Download PDF invoice for an order.
    Customer: own paid/shipped/delivered/refunded orders only.
    Admin: any order in invoiceable status.
    """
    # user_id = _get_user_id(current) <-- REPLACED
    oid_str = str(order_id)
    is_admin = _is_admin(current)
    
    order_repo = AsyncOrderRepository()
    user_repo = AsyncUserRepository()

    # 1. Fetch data asynchronously
    order = await order_repo.get_order_by_id(oid_str)
    if not order: raise HTTPException(404, "Order not found")
        
    # 2. Verify Permissions
    if not is_admin and order.get("customer_id") != user_id:
        raise HTTPException(404, "Order not found")
        
    order_status = order.get("status", "")
    if order_status not in _INVOICEABLE:
        raise HTTPException(409, f"Invoice not available for '{order_status}' orders")
    
    # 3. Fetch Customer Details asynchronously
    customer = await user_repo.get_user_by_id(order.get("customer_id", "")) or {}
    
    # 4. Generate PDF via Threadpool (Crucial for high performance!)
    try:
        # Offload the heavy PDF building task so FastAPI isn't blocked
        pdf_bytes = await run_in_threadpool(build_invoice_pdf, order, customer)
    except Exception as exc:
        logger.error("PDF generation failed | order=%s: %s", oid_str, exc)
        raise HTTPException(500, "Could not generate invoice")
        
    filename = f"Luviio-Invoice-{oid_str[:8].upper()}.pdf"
    logger.info("Invoice downloaded | order=%s size=%d", oid_str, len(pdf_bytes))
    
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Length": str(len(pdf_bytes)),
            "Cache-Control": "no-store",
        },
    )
