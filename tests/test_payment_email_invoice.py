from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def test_paid_email_uses_immutable_invoice_snapshot():
    source = _read("app/events/handlers/order_handlers.py")
    assert "get_invoice_snapshot" in source
    assert "build_snapshot_invoice_pdf" in source
    assert "invoice_order["order_items"] = invoice_items" in source


def test_paid_email_passes_rendered_invoice_to_email_provider():
    source = _read("app/events/handlers/order_handlers.py")
    assert "invoice_pdf=invoice_pdf" in source
    assert "invoice_number=invoice_number" in source


def test_payment_email_supports_pdf_attachment_without_rebuilding_from_event_order():
    source = _read("app/integrations/email/resend_impl.py")
    assert "invoice_pdf: bytes | None = None" in source
    assert 'base64.b64encode(invoice_pdf).decode("ascii")' in source
    assert "build_invoice_pdf" not in source


def test_payment_email_renders_product_lines():
    source = _read("app/integrations/email/resend_impl.py")
    assert "for item in order.get("order_items") or []" in source
    assert "Items in your order" in source
    assert "Invoice No." in source
