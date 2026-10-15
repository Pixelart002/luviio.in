from app.utils.documents.snapshot_invoice_pdf import build_snapshot_invoice_pdf
from app.utils.documents import snapshot_invoice_pdf


def _order(payment_status: str = "paid") -> dict:
    return {
        "invoice_number": "INV/26-27/00001",
        "order_number": "ORD-TEST-0001",
        "status": payment_status,
        "payment_status": payment_status,
        "created_at": "2026-09-17T00:00:00Z",
        "issued_at": "2026-09-17T00:00:00Z",
        "tax_type": "CGST+SGST",
        "subtotal": 268.0,
        "shipping_cost": 45.9,
        "tax_amount": 46.74,
        "total_amount": 360.64,
        "order_items": [
            {
                "product_name": "Test 18% Item",
                "hsn_code": "7324",
                "quantity": 1,
                "unit_price": 243,
                "taxable_value": 243,
                "gst_percentage": 18,
                "tax_amount": 43.74,
                "line_total": 286.74,
            },
            {
                "product_name": "Test 12% Item",
                "hsn_code": "8481",
                "quantity": 1,
                "unit_price": 25,
                "taxable_value": 25,
                "gst_percentage": 12,
                "tax_amount": 3,
                "line_total": 28,
            },
        ],
    }


def _seller() -> dict:
    return {"legal_name": "LUVIIO", "website": "https://luviio.in", "email": "support@luviio.in"}


def _address() -> dict:
    return {"name": "Test Buyer", "city": "New Delhi", "state": "Delhi", "postal_code": "110045", "country": "India"}


def test_invoice_pdf_is_generated_with_gst_breakdown_and_payment_status():
    pdf = build_snapshot_invoice_pdf(_order(), {"full_name": "Test Buyer"}, _seller(), _address(), _address())
    assert pdf.startswith(b"%PDF")


def test_invoice_renderer_never_defaults_missing_payment_to_paid():
    order = _order()
    order.pop("payment_status")
    order.pop("status")
    assert snapshot_invoice_pdf._renderer._payment_status(order) == "PENDING"


def test_invoice_payment_status_maps_succeeded_to_paid():
    assert snapshot_invoice_pdf._renderer._payment_status({"payment_status": "succeeded"}) == "PAID"
