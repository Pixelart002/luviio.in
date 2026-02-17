from fastapi import APIRouter, Request, HTTPException
import resend
import os
import logging

# --- LOGGING SETUP ---
# Wahi logger use kar rahe hain jo main.py mein define kiya tha
logger = logging.getLogger("LUVIIO-APP")
router = APIRouter()

# --- CONFIGURATION ---
RESEND_API_KEY = os.environ.get("RESEND_API_KEY")

if not RESEND_API_KEY:
    logger.error("❌ RESEND_API_KEY is missing in environment variables!")
else:
    resend.api_key = RESEND_API_KEY
    logger.info("✅ Resend API initialized successfully")

# --- OPEN EMAIL ROUTE ---
# URL: /api/resend-mail (Ab koi bhi hit kar sakta hai)
@router.post("/resend-mail")
async def send_email_anywhere(request: Request):
    logger.info(f"📩 New Email Request received from IP: {request.client.host}")
    
    try:
        # 1. Payload Parse aur Log
        payload = await request.json()
        logger.info(f"📦 Payload received: {payload}")
        
        # 2. Email Extract karne ki logic
        # Handle karta hai: Direct JSON {"email": "..."} OR Supabase Webhook {"record": {"email": "..."}}
        if 'record' in payload:
            user_email = payload.get('record', {}).get('email')
        else:
            user_email = payload.get('email')

        if not user_email: 
            logger.warning("⚠️ Request ignored: No email found in payload")
            return {"status": "skipped", "message": "No email provided"}

        logger.info(f"🚀 Preparing to send Waitlist Email to: {user_email}")

        # 3. Email Content (Strictly Professional)
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: sans-serif; background: #000; color: #fff; padding: 20px; text-align: center; }}
                .box {{ border: 1px solid #333; padding: 40px; border-radius: 20px; max-width: 500px; margin: auto; }}
                .btn {{ display: inline-block; background: #fff; color: #000; padding: 12px 24px; text-decoration: none; border-radius: 50px; font-weight: bold; margin-top: 20px; }}
            </style>
        </head>
        <body>
            <div class="box">
                <h1 style="letter-spacing: -1px;">LUVIIO<span style="color: #3b82f6;">.</span></h1>
                <p style="color: #888;">Hi there,</p>
                <p style="font-size: 18px;">You’re officially on the exclusive waitlist for the future of markets.</p>
                <a href="https://x.com/LUVIIO_in" class="btn">Join the Community</a>
            </div>
        </body>
        </html>
        """

        # 4. Actual Send
        params = {
            "from": "Luviio Team <hi@luviio.in>",
            "to": [user_email],
            "subject": "You’re in. Welcome to LUVIIO.",
            "html": html_content,
        }

        email_response = resend.Emails.send(params)
        logger.info(f"✅ Success! Email sent to {user_email}. Resend ID: {email_response}")
        
        return {"status": "success", "email_id": email_response}

    except Exception as e:
        logger.error(f"❌ CRITICAL ERROR in resend_mail: {str(e)}")
        # Internal error ko bhi log kar rahe hain taaki debugging makkhan rahe
        raise HTTPException(status_code=500, detail="Internal Server Error - Check Logs")