import httpx
import logging
from typing import Dict, Optional

logger = logging.getLogger("OAUTH-CLIENT")

class SupabaseOAuthClient:
    def __init__(self, supabase_url: str, supabase_key: str, timeout: float = 10.0):
        self.supabase_url = supabase_url.rstrip('/')
        self.supabase_key = supabase_key
        self.timeout = timeout

    async def exchange_code(self, code: str, verifier: str, redirect_uri: str) -> Dict:
        """
        Exchange authorization code for tokens using PKCE.
        """
        url = f"{self.supabase_url}/auth/v1/token?grant_type=authorization_code"
        headers = {
            "apikey": self.supabase_key,
            "Content-Type": "application/x-www-form-urlencoded"
        }
        data = {
            "code": code,
            "code_verifier": verifier,
            "redirect_uri": redirect_uri
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(url, headers=headers, data=data)
                
                if response.status_code != 200:
                    error_detail = response.json() if response.headers.get("content-type") == "application/json" else response.text
                    logger.error(f"Token exchange failed ({response.status_code}): {error_detail}")
                    return {"success": False, "error": error_detail}
                
                return {"success": True, "data": response.json()}
        except Exception as e:
            logger.error(f"Exception during token exchange: {str(e)}")
            return {"success": False, "error": str(e)}

    async def get_user(self, access_token: str) -> Dict:
        """
        Get user details using the access token.
        """
        url = f"{self.supabase_url}/auth/v1/user"
        headers = {
            "apikey": self.supabase_key,
            "Authorization": f"Bearer {access_token}"
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url, headers=headers)
                if response.status_code != 200:
                    return {"success": False, "error": response.text}
                return {"success": True, "data": response.json()}
        except Exception as e:
            return {"success": False, "error": str(e)}
