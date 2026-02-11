from fastapi import APIRouter, Request, HTTPException, Header, status
import resend
import os

router = APIRouter()

# --- CONFIGURATION ---
RESEND_API_KEY = os.environ.get("RESEND_API_KEY")
# 🔒 New: Admin Secret for Security (Ise Vercel Env Variables mein add karna hoga)
ADMIN_SECRET = os.environ.get("ADMIN_SECRET") 

if not RESEND_API_KEY:
    print("⚠️ WARNING: RESEND_API_KEY is missing")
else:
    resend.api_key = RESEND_API_KEY

# --- SECURE ADMIN ROUTE ---
# URL: https://admin.luviio.in/resend-mail
@router.post("/resend-mail")
async def send_email_securely(
    request: Request,
    # Header se secret key check karein
    x_admin_secret: str = Header(None, alias="x-admin-secret")
):
    # 🔒 LAYER 1: HOST CHECK (Subdomain Restriction)
    # Check karein ki request 'admin.luviio.in' se hi aa rahi hai
    host = request.headers.get("host", "")
    if "admin.luviio.in" not in host:
        # Agar koi 'www' ya kisi aur domain se try kare, toh 404 dikhao
        raise HTTPException(status_code=404, detail="Endpoint not found on this domain")

    # 🔒 LAYER 2: SECURITY CHECK (Block Everyone Else)
    # Agar Secret Key match nahi hui, toh 401 Unauthorized
    if not ADMIN_SECRET or x_admin_secret != ADMIN_SECRET:
        print(f"🛑 Unauthorized Access Attempt from {request.client.host}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, 
            detail="Access Denied: You are not authorized."
        )

    try:
        # 1. Payload Parse
        payload = await request.json()
        
        # NOTE: Agar ye Admin Panel se aa raha hai, toh payload structure simple ho sakta hai
        # Agar Supabase Webhook hai toh 'record' check karein, nahi toh direct 'email'
        if 'record' in payload:
            user_email = payload.get('record', {}).get('email')
        else:
            user_email = payload.get('email')

        if not user_email: 
            return {"status": "skipped", "message": "No email provided"}

        print(f"🚀 Sending Admin Triggered Email to: {user_email}")

        # 2. EMAIL CONTENT
        html_content = """
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <style>
                body { font-family: sans-serif; background: #000; color: #fff; padding: 20px; }
                .box { border: 1px solid #333; padding: 30px; border-radius: 10px; max-width: 500px; margin: auto; }
                .btn { display: inline-block; background: #fff; color: #000; padding: 10px 20px; text-decoration: none; border-radius: 5px; margin-top: 20px; font-weight: bold; }
            </style>
        </head>
        <body>
            <div class="box">
                <h2>LUVIIO<span style="color: #3b82f6;">.</span></h2>
                <p>Hi there,</p>
                <p>You have successfully secured your spot on the exclusive waitlist.</p>
                <a href="https://x.com/LUVIIO_in" class="btn">Follow Updates</a>
            </div>
        </body>
        </html>
        """

        # 3. Send Email
        params = {
            "from": "Luviio Team <hi@luviio.in>",
            "to": [user_email],
            "subject": "You’re in. Welcome to the future of listings.",
            "html": html_content,
        }

        email = resend.Emails.send(params)
        return {"status": "success", "email_id": email}

    except Exception as e:
        print(f"❌ Error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))