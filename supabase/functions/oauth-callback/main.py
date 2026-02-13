"""
Supabase Edge Function: OAuth 2.0 Callback Handler (Python)
Secure server-side token exchange using Authorization Code Flow (PKCE)
Deployed at: https://enqcujmzxtrbfkaungpm.supabase.co/functions/v1/oauth-callback
"""

import os
import json
import logging
from datetime import datetime
from typing import Dict, Optional
import httpx

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("oauth-edge-function")

# Environment variables from Supabase Edge Function context
SB_URL = os.environ.get("SUPABASE_URL")
SB_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
SB_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY")

# Timeout for external requests
REQUEST_TIMEOUT = 10.0


class OAuthCallbackHandler:
    """Handles OAuth 2.0 authorization code exchange securely."""
    
    def __init__(self, supabase_url: str, supabase_key: str):
        self.supabase_url = supabase_url
        self.supabase_key = supabase_key
    
    async def exchange_code_for_session(self, code: str) -> Dict:
        """
        Exchange authorization code for access token & refresh token.
        
        Args:
            code: Authorization code from OAuth provider
            
        Returns:
            Dict with access_token, refresh_token, user data, or error info
        """
        try:
            async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
                response = await client.post(
                    f"{self.supabase_url}/auth/v1/token?grant_type=authorization_code",
                    headers={
                        "apikey": self.supabase_key,
                        "Content-Type": "application/x-www-form-urlencoded"
                    },
                    data={"code": code, "grant_type": "authorization_code"}
                )
            
            if response.status_code not in [200, 201]:
                logger.error(f"Token exchange failed: {response.status_code} - {response.text}")
                return {
                    "success": False,
                    "error": "token_exchange_failed",
                    "message": "Invalid authorization code"
                }
            
            data = response.json()
            return {
                "success": True,
                "access_token": data.get("access_token"),
                "refresh_token": data.get("refresh_token"),
                "expires_in": data.get("expires_in"),
                "user": data.get("user", {})
            }
        
        except httpx.TimeoutException:
            logger.error("Token exchange timeout - Supabase unreachable")
            return {
                "success": False,
                "error": "timeout",
                "message": "Server timeout - try again"
            }
        except Exception as e:
            logger.error(f"Unexpected error during token exchange: {str(e)}")
            return {
                "success": False,
                "error": "server_error",
                "message": "Internal server error"
            }
    
    async def check_or_create_profile(self, user_id: str, email: str) -> Dict:
        """
        Check if user profile exists. If not, create one.
        Implements State A (New User) logic.
        
        Args:
            user_id: Supabase user ID
            email: User email
            
        Returns:
            Dict with profile status and onboarding state
        """
        try:
            # Check if profile exists
            async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
                check_res = await client.get(
                    f"{self.supabase_url}/rest/v1/profiles?id=eq.{user_id}&select=*",
                    headers={
                        "apikey": self.supabase_key,
                        "Authorization": f"Bearer {self.supabase_key}",
                        "Content-Type": "application/json"
                    }
                )
            
            if check_res.status_code == 200:
                profiles = check_res.json()
                if profiles:
                    # STATE B/C: Profile exists
                    onboarded = profiles[0].get("onboarded", False)
                    logger.info(f"Profile found for {email} - Onboarded: {onboarded}")
                    return {
                        "success": True,
                        "action": "existing_profile",
                        "onboarded": onboarded,
                        "next_url": "/dashboard" if onboarded else "/onboarding"
                    }
            
            # STATE A: Create new profile
            async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
                create_res = await client.post(
                    f"{self.supabase_url}/rest/v1/profiles",
                    headers={
                        "apikey": self.supabase_key,
                        "Authorization": f"Bearer {self.supabase_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "id": user_id,
                        "email": email,
                        "onboarded": False,
                        "created_at": datetime.utcnow().isoformat()
                    }
                )
            
            if create_res.status_code in [200, 201]:
                logger.info(f"New profile created for {email}")
                return {
                    "success": True,
                    "action": "new_profile",
                    "onboarded": False,
                    "next_url": "/onboarding"
                }
            else:
                logger.warning(f"Profile creation failed: {create_res.status_code}")
                return {
                    "success": True,
                    "action": "new_profile",
                    "onboarded": False,
                    "next_url": "/onboarding"
                }
        
        except Exception as e:
            logger.error(f"Profile check/create error: {str(e)}")
            return {
                "success": True,
                "action": "profile_error",
                "onboarded": False,
                "next_url": "/onboarding"  # Failsafe
            }


def handler(req):
    """Main Edge Function handler."""
    
    # ===== INPUT VALIDATION =====
    if not SB_URL or not SB_SERVICE_KEY:
        logger.critical("Missing Supabase environment variables")
        return {
            "statusCode": 500,
            "body": json.dumps({
                "error": "server_misconfigured",
                "message": "OAuth service temporarily unavailable"
            }),
            "headers": {"Content-Type": "application/json"}
        }
    
    # Extract query parameters
    code = req.get("code")
    error = req.get("error")
    error_description = req.get("error_description")
    
    # Handle OAuth provider errors
    if error:
        logger.warning(f"OAuth Provider Error: {error} - {error_description}")
        return {
            "statusCode": 302,
            "headers": {
                "Location": f"/login?error={error}&msg={error_description or 'Authorization failed'}"
            }
        }
    
    if not code:
        logger.warning("OAuth Callback: No authorization code received")
        return {
            "statusCode": 302,
            "headers": {
                "Location": "/login?error=no_code&msg=Authorization+failed"
            }
        }
    
    # ===== ASYNC HANDLER =====
    import asyncio
    
    async def process_oauth():
        handler_obj = OAuthCallbackHandler(SB_URL, SB_SERVICE_KEY)
        
        # Step 1: Exchange code for session
        token_result = await handler_obj.exchange_code_for_session(code)
        
        if not token_result.get("success"):
            return {
                "statusCode": 302,
                "headers": {
                    "Location": f"/login?error={token_result.get('error')}&msg={token_result.get('message')}"
                }
            }
        
        user_id = token_result.get("user", {}).get("id")
        email = token_result.get("user", {}).get("email", "unknown")
        access_token = token_result.get("access_token")
        refresh_token = token_result.get("refresh_token")
        
        if not user_id or not access_token:
            logger.error("Token response missing critical data")
            return {
                "statusCode": 302,
                "headers": {
                    "Location": "/login?error=invalid_response"
                }
            }
        
        # Step 2: Check/Create profile
        profile_result = await handler_obj.check_or_create_profile(user_id, email)
        next_url = profile_result.get("next_url", "/onboarding")
        
        logger.info(f"OAuth successful for {email} → {next_url}")
        
        # Step 3: Set secure cookies and redirect
        response_headers = {
            "Location": next_url,
            "Set-Cookie": [
                f"sb-access-token={access_token}; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=3600",
                f"sb-refresh-token={refresh_token}; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=2592000"
            ]
        }
        
        return {
            "statusCode": 302,
            "headers": response_headers
        }
    
    # Execute async function
    return asyncio.run(process_oauth())
