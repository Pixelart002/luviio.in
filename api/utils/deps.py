import logging
from datetime import datetime, timezone
from fastapi import Request, HTTPException, Depends, status
from jose import jwt, JWTError, ExpiredSignatureError

# --- INTERNAL MODULES ---
from api.utils.security import SECRET_KEY, ALGORITHM
from api.routes.database import supabase_admin

# --- 🪵 ELITE LOGGING CONFIG ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s.%(msecs)03d | 🛡️ DEPS-GUARD | %(levelname)s | %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger("SECURITY-GUARD")

async def get_current_user(request: Request) -> dict:
    """
    ULTRA-SECURE AUTH GUARD:
    1. Validates JWT Signature.
    2. Cross-references Session ID in Supabase (Source of Truth).
    3. Prevents Session Hijacking via IP/UA Fingerprinting.
    """
    
    # 1. 📥 EXTRACT TRIPLE-COOKIES
    access_token = request.cookies.get("access_token")
    refresh_token = request.cookies.get("refresh_token")
    session_id = request.cookies.get("session_id")
    
    # Client identifiers for fingerprinting
    client_ip = request.client.host
    user_agent = request.headers.get("user-agent", "unknown")

    # Guard: Missing Core Cookies
    if not access_token or not session_id:
        logger.warning(f"🚫 [AUTH-FAIL] Missing credentials from {client_ip}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session cookies missing. Please login again."
        )

    try:
        # 2. 🔐 JWT CRYPTOGRAPHIC VALIDATION
        logger.info(f"🔍 [JWT-CHECK] Verifying access token for session {session_id[:8]}...")
        payload = jwt.decode(access_token, SECRET_KEY, algorithms=[ALGORITHM])
        
        user_id: str = payload.get("sub")
        token_type: str = payload.get("type")

        if user_id is None or token_type != "access":
            raise JWTError("Malformed token payload")
            
    except ExpiredSignatureError:
        logger.info(f"⏳ [JWT-EXPIRED] Access token dead for session {session_id[:8]}")
        # Hint to frontend: Token expired, try /refresh
        raise HTTPException(status_code=401, detail="token_expired")
        
    except JWTError as e:
        logger.error(f"❌ [JWT-CORRUPT] Critical JWT failure: {str(e)}")
        raise HTTPException(status_code=401, detail="Invalid session signature")

    # 3. 🗄️ DATABASE-BACKED SESSION VALIDATION (The "Ultrabeast" Layer)
    # We don't just trust the JWT; we check if the session is alive in DB
    logger.info(f"🗃️ [DB-SYNC] Verifying session {session_id} in Supabase...")
    
    res = supabase_admin.table("sessions").select("*, users(*)").eq("id", session_id).single().execute()
    session_record = res.data

    if not session_record:
        logger.error(f"🚨 [DB-FAIL] Session {session_id} does not exist in DB!")
        raise HTTPException(status_code=401, detail="Session invalidated")

    # Check: Revocation Status
    if session_record.get("is_revoked"):
        logger.warning(f"🚫 [REVOKED] Blocked access for revoked session: {session_id}")
        raise HTTPException(status_code=401, detail="Session has been terminated")

    # Check: Database Expiry
    db_expiry = datetime.fromisoformat(session_record["expires_at"].replace('Z', '+00:00'))
    if db_expiry < datetime.now(timezone.utc):
        logger.warning(f"⏰ [EXPIRED] Session entry in DB has timed out.")
        raise HTTPException(status_code=401, detail="Session expired")

    # 4. 👤 USER OBJECT RECOVERY
    user = session_record.get("users")
    if not user:
        logger.critical(f"💀 [ORPHAN-SESSION] Session exists but User {user_id} is missing!")
        raise HTTPException(status_code=401, detail="Identity sync error")

    logger.info(f"✅ [AUTH-SUCCESS] User {user['email']} verified via session {session_id[:8]}")
    return user

async def require_onboarded(user: dict = Depends(get_current_user)) -> dict:
    """
    Middleware: Ensures the user is not just authenticated, but has finished /onboarding.
    Use this on Dashboard and Feature routes.
    """
    logger.info(f"🚀 [CHECK-ONBOARD] Status for user: {user['email']}")
    
    if not user.get("onboarded"):
        logger.warning(f"⚠️ [REDIRECT] User {user['email']} is trying to skip onboarding!")
        raise HTTPException(
            status_code=status.HTTP_307_TEMPORARY_REDIRECT, 
            detail="onboarding_required"
        )
    
    return user