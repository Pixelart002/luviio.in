import httpx
import logging
import time
from typing import Dict, Optional, Any, Tuple

# Configure structured logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ENTERPRISE-AUTH")

class SupabaseAuthClient:
    """
    Enterprise-level Supabase Auth Client.
    Handles PKCE exchange, token management, and user profiling.
    """
    def __init__(self, supabase_url: str, supabase_key: str, timeout: float = 15.0):
        self.url = supabase_url.rstrip('/')
        self.key = supabase_key
        self.timeout = timeout
        self.base_headers = {
            "apikey": self.key,
            "Content-Type": "application/json"
        }

    async def _request(self, method: str, path: str, **kwargs) -> Tuple[bool, Any]:
        """Centralized request handler with error wrapping."""
        full_url = f"{self.url}{path}"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.request(method, full_url, **kwargs)
                data = response.json() if response.headers.get("content-type") == "application/json" else response.text
                
                if response.is_success:
                    return True, data
                
                logger.error(f"Auth API Error [{response.status_code}] at {path}: {data}")
                return False, data
        except Exception as e:
            logger.exception(f"Unexpected Exception at {path}: {str(e)}")
            return False, str(e)

    async def exchange_code_for_token(self, code: str, verifier: str, redirect_uri: str) -> Dict:
        """Exchanges authorization code for session tokens using PKCE."""
        logger.info(f"Initiating token exchange for code: {code[:5]}...")
        
        payload = {
            "code": code,
            "code_verifier": verifier,
            "redirect_uri": redirect_uri
        }
        
        success, data = await self._request(
            "POST", 
            "/auth/v1/token?grant_type=authorization_code", 
            json=payload,
            headers=self.base_headers
        )
        
        if success:
            logger.info("Token exchange successful.")
            return {"success": True, "tokens": data}
        return {"success": False, "error": data}

    async def refresh_session(self, refresh_token: str) -> Dict:
        """Refreshes an expired access token using a refresh token."""
        logger.info("Attempting session refresh...")
        payload = {
            "refresh_token": refresh_token
        }
        
        success, data = await self._request(
            "POST",
            "/auth/v1/token?grant_type=refresh_token",
            json=payload,
            headers=self.base_headers
        )
        
        if success:
            logger.info("Session refresh successful.")
            return {"success": True, "tokens": data}
        return {"success": False, "error": data}

    async def get_user_profile(self, access_token: str) -> Dict:
        """Retrieves user profile and verifies token validity."""
        headers = {**self.base_headers, "Authorization": f"Bearer {access_token}"}
        success, data = await self._request("GET", "/auth/v1/user", headers=headers)
        
        if success:
            return {"success": True, "user": data}
        return {"success": False, "error": data}
