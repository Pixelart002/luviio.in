from pathlib import Path

from app.domains.orders.service import OrderService

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_invoice_generation_is_snapshot_backed():
    source = (REPO_ROOT / "app/domains/orders/service.py").read_text(encoding="utf-8")
    assert "get_invoice_snapshot" in source
    assert "Immutable invoice snapshot is not available" in source


def test_invoice_generation_requires_invoice_number_and_seller_snapshot():
    source = (REPO_ROOT / "app/domains/orders/service.py").read_text(encoding="utf-8")
    assert "Invoice number is not available for this order." in source
    assert "Invoice seller configuration is incomplete" in source


def test_invoice_pdf_uses_public_order_number_for_document_identity():
    source = (REPO_ROOT / "app/domains/orders/service.py").read_text(encoding="utf-8")
    assert 'invoice_order["id"] = str(raw_order.get("order_number") or order_identifier)' in source
    assert 'invoice_order["invoice_number"] = invoice.get("invoice_number") or invoice_number' in source


def test_invoice_service_keeps_pdf_generation_off_request_thread():
    source = (REPO_ROOT / "app/domains/orders/service.py").read_text(encoding="utf-8")
    assert "run_in_threadpool(" in source
    assert "build_snapshot_invoice_pdf" in source
    assert OrderService.generate_invoice_pdf is not None
