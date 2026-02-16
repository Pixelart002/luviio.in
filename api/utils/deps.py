import logging
import os
from fastapi import Request, HTTPException, Depends, status
from jose import jwt, JWTError, ExpiredSignatureError
from api.utils.security import SECRET_KEY, ALGORITHM
from api.routes.database import supabase_admin

# --- 🪵 PRODUCTION LOGGING SETUP ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("AUTH-MIDDLEWARE")

async def get_current_user(request: Request):
    """
    Strictly validates the Access Token from HttpOnly cookies.
    Simplified for single-domain (luviio.in) usage.
    """
    
    access_token = request.cookies.get("access_token")
    refresh_token = request.cookies.get("refresh_token")
    
    # 1. Check: Token Presence
    if not access_token:
        if refresh_token:
            logger.info("🔄 Hint: Access token missing but Refresh token found. Triggering background refresh.")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="token_expired", 
                headers={"WWW-Authenticate": "Bearer realm='token_expired'"}
            )
        
        logger.warning("🚫 Access Denied: No session cookies found in request")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated"
        )

    try:
        # 2. JWT Decoding & Validation
        logger.info("🔍 Step: Verifying JWT signature with SESSION_SECRET")
        payload = jwt.decode(access_token, SECRET_KEY, algorithms=[ALGORITHM])
        
        user_id: str = payload.get("sub")
        token_type: str = payload.get("type")

        if user_id is None or token_type != "access":
            logger.error(f"❌ Error: Invalid token payload format for user {user_id}")
            raise HTTPException(status_code=401, detail="Invalid token")
            
    except ExpiredSignatureError:
        # Access token expire hone par refresh hint dein
        if refresh_token:
            logger.info("⏳ Hint: Access token expired. Refresh token available.")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="token_expired"
            )
        raise HTTPException(status_code=401, detail="Session expired")
        
    except JWTError as e:
        logger.error(f"❌ Error: JWT Verification failed: {str(e)}")
        raise HTTPException(status_code=401, detail="Invalid session")

    # 3. Admin-Level DB Sync (Bypassing RLS for reliable auth)
    logger.info(f"🗄️ Step: Fetching User {user_id} data via Service Role")
    
    # Single-domain mein database query seedha aur tez hoti hai
    user_res = supabase_admin.table("users").select("*").eq("id", user_id).execute()

    if not user_res.data:
        logger.error(f"❌ Error: User {user_id} not found in Database")
        raise HTTPException(status_code=401, detail="User not found")

    user = user_res.data[0]
    logger.info(f"✅ Success: User {user['email']} authenticated")
    
    return user

async def require_onboarded(user: dict = Depends(get_current_user)):
    """
    Middleware: Ensures the user is logged in AND has completed onboarding.
    Triggers 'onboarding_required' for single-domain redirection.
    """
    logger.info(f"🚀 Step: Checking onboarding status for {user['email']}")
    
    if not user.get("onboarded"):
        logger.warning(f"⚠️ Access Blocked: {user['email']} has not finished onboarding")
        
        # 🔥 TRIGGER: Detail catch karke main.py user ko /onboarding par bhejega
        raise HTTPException(
            status_code=status.HTTP_307_TEMPORARY_REDIRECT, 
            detail="onboarding_required"
        )
    
    logger.info(f"✅ Success: Onboarding confirmed for {user['email']}")
    return user