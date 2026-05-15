"""
main.py additions
=================
Add these 3 things to your existing app/main.py.
Search for the existing import/router blocks and add alongside them.

─────────────────────────────────────────────────────────────────────────────
STEP 1 — Add to imports (after existing router imports)
─────────────────────────────────────────────────────────────────────────────

from app.routers import cart, pricing, invoice

─────────────────────────────────────────────────────────────────────────────
STEP 2 — Add to router registrations (after existing app.include_router calls)
─────────────────────────────────────────────────────────────────────────────

PREFIX = "/api/v1"   # already defined in your main.py

app.include_router(cart.router,    prefix=PREFIX)
app.include_router(pricing.router, prefix=PREFIX)
app.include_router(invoice.router, prefix=PREFIX)

─────────────────────────────────────────────────────────────────────────────
STEP 3 — Add to requirements.txt
─────────────────────────────────────────────────────────────────────────────

reportlab==4.2.2

─────────────────────────────────────────────────────────────────────────────
File placement guide
─────────────────────────────────────────────────────────────────────────────

app/
├── routers/
│   ├── cart.py          ← new  (this output)
│   ├── pricing.py       ← new  (this output)
│   └── invoice.py       ← new  (this output)
└── utils/
    └── pdf_invoice.py   ← new  (this output)

migrations_cart_pricing.sql   ← run once in Supabase SQL Editor

─────────────────────────────────────────────────────────────────────────────
email.py addition — send_cart_reminder_email()
─────────────────────────────────────────────────────────────────────────────
Add this function to your existing app/utils/email.py:
"""

# ── Paste this function into app/utils/email.py ───────────────────────────────

CART_REMINDER_EMAIL_SNIPPET = '''
def send_cart_reminder_email(to: str, name: str, items: list) -> None:
    """Send abandoned cart reminder. Called from cart.py admin remind endpoint."""
    name = name or "there"

    # Build item rows HTML
    item_rows = ""
    for item in items:
        prod = item.get("products") or {}
        prod_name = prod.get("name", "Product")
        qty = item.get("quantity", 1)
        price = item.get("price_snapshot", 0)
        item_rows += f"""
        <tr>
          <td style="padding:8px 0;color:#333;font-size:13px;">{prod_name}</td>
          <td style="padding:8px 0;text-align:center;font-size:13px;">{qty}</td>
          <td style="padding:8px 0;text-align:right;font-size:13px;font-weight:600;">₹{float(price):.2f}</td>
        </tr>"""

    params: resend.Emails.SendParams = {
        "from":    FROM,
        "to":      [to],
        "subject": f"You left something behind, {name}! 🛒",
        "html": f"""
<!DOCTYPE html><html>
<body style="margin:0;padding:0;background:#f4f4f4;font-family:sans-serif;">
<div style="max-width:520px;margin:40px auto;background:#fff;border-radius:10px;overflow:hidden;">
  <div style="background:#0B1628;padding:28px 32px;">
    <h1 style="color:#00C5D4;font-size:22px;margin:0;letter-spacing:2px;">{APP.upper()}</h1>
  </div>
  <div style="padding:32px;">
    <h2 style="color:#0B1628;margin-top:0;">Your cart is waiting, {name}!</h2>
    <p style="color:#555;line-height:1.7;">
      You left some items in your cart. Complete your purchase before they sell out!
    </p>
    <table style="width:100%;border-collapse:collapse;margin:20px 0;">
      <tr style="border-bottom:2px solid #0B1628;">
        <th style="padding:8px 0;text-align:left;font-size:12px;color:#888;">PRODUCT</th>
        <th style="padding:8px 0;text-align:center;font-size:12px;color:#888;">QTY</th>
        <th style="padding:8px 0;text-align:right;font-size:12px;color:#888;">PRICE</th>
      </tr>
      {item_rows}
    </table>
    <a href="https://luviio.in/cart"
       style="display:inline-block;margin-top:20px;padding:14px 32px;
              background:#0B1628;color:#fff;border-radius:8px;
              text-decoration:none;font-weight:600;letter-spacing:1px;font-size:14px;">
      Complete Your Order →
    </a>
    <p style="color:#aaa;font-size:11px;margin-top:28px;">
      If you no longer wish to receive these emails, you can ignore this message.
    </p>
  </div>
</div>
</body></html>""",
    }
    try:
        email = resend.Emails.send(params)
        email_id = email.get("id") if isinstance(email, dict) else getattr(email, "id", "unknown")
        logger.info("Cart reminder email sent | to=%s id=%s", to, email_id)
    except Exception as e:
        logger.error("Cart reminder email failed | to=%s | %s", to, e, exc_info=True)
'''

# ─────────────────────────────────────────────────────────────────────────────
# New API endpoints summary
# ─────────────────────────────────────────────────────────────────────────────
NEW_ENDPOINTS = """
PRICING  /api/v1/pricing
  POST /calculate   — server-side tax+shipping (single source of truth)
  GET  /config      — current rates (for frontend banners)

CART  /api/v1/cart
  GET    /                          — get cart with live pricing
  POST   /items                     — add item (upserts quantity)
  PUT    /items/{product_id}        — set exact quantity
  DELETE /items/{product_id}        — remove item
  DELETE /                          — clear cart

  🔒 Admin:
  GET    /admin/abandoned            — carts not updated in 24h (with items)
  POST   /admin/remind/{cart_id}     — push + email reminder to cart owner

INVOICE  /api/v1/orders/{order_id}/invoice
  GET    /orders/{order_id}/invoice  — stream tamper-proof PDF (paid orders only)
"""

if __name__ == "__main__":
    print(NEW_ENDPOINTS)