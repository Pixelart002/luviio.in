from fastapi import APIRouter, Request
import resend
import os

# ⚠️ Dhyan de: Yahan 'app = FastAPI()' NAHI hona chahiye.
# Yahan 'router = APIRouter()' hona chahiye.
router = APIRouter()

# --- CONFIGURATION ---
RESEND_API_KEY = os.environ.get("RESEND_API_KEY")

if not RESEND_API_KEY:
    print("⚠️ WARNING: RESEND_API_KEY is missing via Environment Variables")

resend.api_key = RESEND_API_KEY

# --- WEBHOOK ROUTE ---
@router.post("/webhook/send-email")
async def handle_supabase_webhook(request: Request):
    try:
        # 1. Supabase se data lena
        payload = await request.json()
        record = payload.get('record', {})
        user_email = record.get('email')

        # Agar email nahi mila to skip karo
        if not user_email: 
            return {"status": "skipped", "message": "No email found"}

        print(f"Sending welcome email to: {user_email}")

        # 2. PROFESSIONAL HTML CONTENT
        html_content = """
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <style>
                body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; background-color: #f9f9f9; margin: 0; padding: 0; }
                .container { max-width: 600px; margin: 40px auto; background: #ffffff; padding: 40px; border-radius: 8px; box-shadow: 0 4px 10px rgba(0,0,0,0.05); }
                .btn { display: inline-block; background-color: #000000; color: #ffffff; padding: 12px 24px; text-decoration: none; border-radius: 6px; font-weight: 600; margin-top: 20px; }
            </style>
        </head>
        <body>
            <div class="container">
                <h2 style="margin-top: 0; color: #000;">LUVIIO</h2>
                <h3 style="color: #333;">You’re in. Welcome to the future of listings.</h3>
                <p style="color: #555; line-height: 1.6;">Hi there,</p>
                <p style="color: #555; line-height: 1.6;">You have successfully secured your spot on the exclusive waitlist for Luviio.</p>
                <p style="color: #555; line-height: 1.6;">The current marketplace ecosystem faces a critical trust deficit. We are rebuilding the foundation. You are now part of a select group waiting for the new <strong>Operating System for Listings</strong>.</p>
                <a href="https://x.com/LUVIIO_in" class="btn">Follow updates on X</a>
                <p style="margin-top: 30px; font-size: 12px; color: #999;">&copy; 2026 Luviio Technologies.</p>
            </div>
        </body>
        </html>
        """

        # 3. Email bhejna (Resend ke through)
        params = {
            "from": "Luviio Team <no-reply@luviio.in>",
            "to": [user_email],
            "subject": "You’re in. Welcome to the future of listings.",
            "html": html_content,
        }

        email = resend.Emails.send(params)
        print(f"✅ Email Sent Successfully! ID: {email}")
        
        return {"status": "success", "email_id": email}

    except Exception as e:
        print(f"❌ Error sending email: {str(e)}")
        return {"status": "error", "details": str(e)}