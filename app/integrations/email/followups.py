"""Post-delivery customer follow-up emails."""
from __future__ import annotations
import html, os
import resend
from starlette.concurrency import run_in_threadpool

FROM = os.getenv("RESEND_FROM", "Luviio <noreply@luviio.in>")
BASE_URL = os.getenv("PUBLIC_APP_URL", "https://luviio.in").rstrip("/")

async def _send(to: str, subject: str, title: str, body: str, url: str) -> bool:
    key = os.getenv("RESEND_API_KEY", "").strip()
    if not key or not to:
        return False
    safe_body = html.escape(body)
    params = {
        "from": FROM, "to": [to], "subject": subject,
        "html": f"""<!doctype html><html><body style="font-family:Arial,sans-serif;background:#080808;color:#f5f1ea;padding:32px">
        <div style="max-width:560px;margin:auto;border:1px solid #2a2a2a;border-radius:14px;padding:28px;background:#111">
        <div style="letter-spacing:4px;font-weight:700;color:#d8ad6a">LUVIIO</div>
        <h2>{html.escape(title)}</h2><p style="line-height:1.7;color:#bbb">{safe_body}</p>
        <a href="{html.escape(url, quote=True)}" style="display:inline-block;padding:12px 22px;background:#d8ad6a;color:#080808;text-decoration:none;border-radius:8px;font-weight:700">Open Luviio</a>
        </div></body></html>""",
    }
    try:
        await run_in_threadpool(resend.Emails.send, params)
        return True
    except Exception:
        return False

async def send_review_followup(to: str, order_number: str, product_name: str | None = None) -> bool:
    item = f" about {product_name}" if product_name else ""
    return await _send(to, f"How was your Luviio order #{order_number}?", "How was your order?", f"Your order #{order_number} has been delivered. We would love to hear your feedback{item}.", f"{BASE_URL}/orders/{order_number}")

async def send_delivery_care_followup(to: str, order_number: str) -> bool:
    return await _send(to, f"Need help with order #{order_number}?", "Everything arrived okay?", f"If you need help with order #{order_number}, our support team is here. You can review the order details and contact support if anything needs attention.", f"{BASE_URL}/orders/{order_number}")
