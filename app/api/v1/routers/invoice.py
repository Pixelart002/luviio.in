"""
Invoice Router — Async Enterprise Grade
=======================================
Path: app/api/v1/routers/invoice.py
"""
import io
from uuid import UUID
from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import StreamingResponse

from app.core.dependencies import get_current_user, get_user_id_strict
from app.services.order.service import OrderService
from app.enums.roles import UserRole

router = APIRouter(prefix="/orders", tags=["Invoice"])

@router.get("/{order_id}/invoice", status_code=status.HTTP_200_OK)
async def download_invoice(
    request: Request, 
    order_id: UUID, 
    current: dict = Depends(get_current_user), 
    user_id: str = Depends(get_user_id_strict)
):
    """
    Streams a dynamically generated PDF Tax Invoice.
    ABAC Guarded: Only the order owner or system admins can download it.
    """
    if hasattr(request.state, "actions"): 
        request.state.actions.append(f"Targeting Invoice download for Order: {str(order_id)[:8]}...")
    
    # Resolve role for ABAC override
    is_admin = current.get("profile", {}).get("role") in [UserRole.ADMIN.value, UserRole.SUPER_ADMIN.value, UserRole.MANAGER.value]
    
    # OrderService's generate_invoice_pdf inherently handles ABAC and HTTP 404/403/409 exceptions.
    pdf_bytes = await OrderService().generate_invoice_pdf(str(order_id), user_id, is_admin)
    
    filename = f"Luviio-Invoice-{str(order_id)[:8].upper()}.pdf"
    if hasattr(request.state, "actions"): 
        request.state.actions.append(f"Prepared Streaming attachment: '{filename}'")

    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"', 
            "Content-Length": str(len(pdf_bytes)), 
            "Cache-Control": "no-store"
        },
    )