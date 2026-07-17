import io
from uuid import UUID
from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from app.core.dependencies import get_current_user, get_user_id_strict
from app.services.orders.service import OrderService
from app.enums.roles import UserRole

router = APIRouter(prefix="/orders", tags=["Invoice"])

@router.get("/{order_id}/invoice")
async def download_invoice(request: Request, order_id: UUID, current: dict = Depends(get_current_user), user_id: str = Depends(get_user_id_strict)):
    if hasattr(request.state, "actions"): request.state.actions.append(f"Targeting Invoice download for Order: {str(order_id)[:8]}...")
    
    is_admin = current.get("profile", {}).get("role") in [UserRole.ADMIN, UserRole.SUPER_ADMIN, UserRole.MANAGER]
    pdf_bytes = await OrderService().generate_invoice_pdf(str(order_id), user_id, is_admin)
    
    filename = f"Luviio-Invoice-{str(order_id)[:8].upper()}.pdf"
    if hasattr(request.state, "actions"): request.state.actions.append(f"Prepared Streaming attachment: '{filename}'")

    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"', "Content-Length": str(len(pdf_bytes)), "Cache-Control": "no-store"},
    )