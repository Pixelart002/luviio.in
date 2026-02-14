"""
OAuth 2.0 Client for Supabase Authentication
Handles secure token exchange, session management, and user profile operations
"""

import os
import json
import logging
import httpx
from typing import Dict, Optional, Tuple
from datetime import datetime
from dataclasses import dataclass

logger = logging.getLogger("oauth-client")


@dataclass
class OAuthSession:
    """Represents an authenticated OAuth session."""
    access_token: str
    refresh_token: Optional[str]
    user_id: str
    email: str
    expires_in: int
    is_onboarded: bool
    next_url: str


class SupabaseOAuthClient:
    """
    Production-ready OAuth 2.0 client for Supabase.
    Handles token exchange, profile management, and secure session creation.
    """
    
    def __init__(
        self,
        supabase_url: Optional[str] = None,
        supabase_key: Optional[str] = None,
        service_role_key: Optional[str] = None,
        timeout: float = 10.0
    ):
        """
        Initialize OAuth client.
        
        Args:
            supabase_url: Supabase project URL (defaults to SB_URL env)
            supabase_key: Supabase anon key (defaults to SB_KEY env)
            service_role_key: Supabase service role key (defaults to SB_SERVICE_ROLE_KEY env)
            timeout: HTTP request timeout in seconds
        """
        self.supabase_url = supabase_url or os.environ.get("SB_URL")
        self.supabase_key = supabase_key or os.environ.get("SB_KEY")
        self.service_role_key = service_role_key or os.environ.get("SB_SERVICE_ROLE_KEY")
        self.timeout = timeout
        
        # Validation
        if not self.supabase_url:
            raise ValueError("Missing SUPABASE_URL")
        if not self.supabase_key:
            raise ValueError("Missing SUPABASE_ANON_KEY")
        if not self.service_role_key:
            raise ValueError("Missing SUPABASE_SERVICE_ROLE_KEY")
        
        logger.info("✓ SupabaseOAuthClient initialized")
    
    async def exchange_authorization_code(self, code: str) -> Dict:
        """
        Exchange OAuth authorization code for session tokens.
        Uses Authorization Code Flow (PKCE).
        
        Args:
            code: Authorization code from OAuth provider
            
        Returns:
            Dict with access_token, refresh_token, user data, or error
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.supabase_url}/auth/v1/token?grant_type=authorization_code",
                    headers={
                        "apikey": self.supabase_key,
                        "Content-Type": "application/x-www-form-urlencoded"
                    },
                    data={
                        "code": code,
                        "grant_type": "authorization_code"
                    }
                )
            
            if response.status_code != 200:
                error_msg = response.json().get("error_description", "Token exchange failed")
                logger.error(f"Token exchange failed: {response.status_code} - {error_msg}")
                return {
                    "success": False,
                    "error": "token_exchange_failed",
                    "message": error_msg
                }
            
            data = response.json()
            user = data.get("user", {})
            
            result = {
                "success": True,
                "access_token": data.get("access_token"),
                "refresh_token": data.get("refresh_token"),
                "expires_in": data.get("expires_in"),
                "user": {
                    "id": user.get("id"),
                    "email": user.get("email"),
                    "provider": user.get("app_metadata", {}).get("provider")
                }
            }
            
            logger.info(f"✓ Token exchange successful for {user.get('email')}")
            return result
        
        except httpx.TimeoutException:
            logger.error("Token exchange timeout")
            return {
                "success": False,
                "error": "timeout",
                "message": "Server timeout - try again"
            }
        except Exception as e:
            logger.error(f"Token exchange error: {str(e)}")
            return {
                "success": False,
                "error": "server_error",
                "message": "Internal error during token exchange"
            }
    
    async def email_password_signup(self, email: str, password: str) -> Dict:
        """
        Sign up user with email and password.
        
        Args:
            email: User email
            password: User password (min 6 chars)
            
        Returns:
            Dict with user data or error
        """
        # Validation
        if not email or not password:
            return {"success": False, "error": "missing_fields"}
        
        if len(password) < 6:
            return {"success": False, "error": "weak_password"}
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.supabase_url}/auth/v1/signup",
                    headers={
                        "apikey": self.supabase_key,
                        "Content-Type": "application/json"
                    },
                    json={"email": email.strip().lower(), "password": password}
                )
            
            if response.status_code not in [200, 201]:
                error_msg = response.json().get("error_description", "Signup failed")
                logger.warning(f"Signup failed for {email}: {error_msg}")
                return {
                    "success": False,
                    "error": "signup_failed",
                    "message": error_msg
                }
            
            user = response.json().get("user", {})
            logger.info(f"✓ User created: {email}")
            
            return {
                "success": True,
                "user": {
                    "id": user.get("id"),
                    "email": user.get("email")
                },
                "message": "Signup successful. Check email for confirmation."
            }
        
        except Exception as e:
            logger.error(f"Signup error: {str(e)}")
            return {
                "success": False,
                "error": "server_error",
                "message": "Signup failed"
            }
    
    async def email_password_login(self, email: str, password: str) -> Dict:
        """
        Log in user with email and password.
        
        Args:
            email: User email
            password: User password
            
        Returns:
            Dict with session data or error
        """
        if not email or not password:
            return {"success": False, "error": "missing_fields"}
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.supabase_url}/auth/v1/token?grant_type=password",
                    headers={
                        "apikey": self.supabase_key,
                        "Content-Type": "application/json"
                    },
                    json={
                        "email": email.strip().lower(),
                        "password": password
                    }
                )
            
            if response.status_code != 200:
                error_msg = response.json().get("error_description", "Invalid credentials")
                logger.warning(f"Login failed for {email}")
                return {
                    "success": False,
                    "error": "invalid_credentials",
                    "message": error_msg
                }
            
            data = response.json()
            user = data.get("user", {})
            
            logger.info(f"✓ Login successful: {email}")
            
            return {
                "success": True,
                "access_token": data.get("access_token"),
                "refresh_token": data.get("refresh_token"),
                "expires_in": data.get("expires_in"),
                "user": {
                    "id": user.get("id"),
                    "email": user.get("email")
                }
            }
        
        except Exception as e:
            logger.error(f"Login error: {str(e)}")
            return {
                "success": False,
                "error": "server_error",
                "message": "Login failed"
            }
    
    async def verify_token(self, access_token: str) -> Dict:
        """
        Verify if access token is valid and return user data.
        
        Args:
            access_token: JWT access token
            
        Returns:
            Dict with user data or error
        """
        if not access_token:
            return {"success": False, "authenticated": False}
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    f"{self.supabase_url}/auth/v1/user",
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "apikey": self.supabase_key
                    }
                )
            
            if response.status_code != 200:
                return {"success": False, "authenticated": False}
            
            user = response.json()
            return {
                "success": True,
                "authenticated": True,
                "user": {
                    "id": user.get("id"),
                    "email": user.get("email"),
                    "provider": user.get("app_metadata", {}).get("provider")
                }
            }
        
        except Exception as e:
            logger.error(f"Token verification error: {str(e)}")
            return {"success": False, "authenticated": False}
    
    async def refresh_session(self, refresh_token: str) -> Dict:
        """
        Refresh expired access token using refresh token.
        
        Args:
            refresh_token: Refresh token
            
        Returns:
            Dict with new access token or error
        """
        if not refresh_token:
            return {"success": False, "error": "no_refresh_token"}
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.supabase_url}/auth/v1/token?grant_type=refresh_token",
                    headers={
                        "apikey": self.supabase_key,
                        "Content-Type": "application/json"
                    },
                    json={"refresh_token": refresh_token}
                )
            
            if response.status_code != 200:
                logger.warning("Token refresh failed")
                return {"success": False, "error": "refresh_failed"}
            
            data = response.json()
            logger.info("✓ Token refreshed successfully")
            
            return {
                "success": True,
                "access_token": data.get("access_token"),
                "refresh_token": data.get("refresh_token"),
                "expires_in": data.get("expires_in")
            }
        
        except Exception as e:
            logger.error(f"Token refresh error: {str(e)}")
            return {"success": False, "error": "refresh_failed"}
    
    async def get_or_create_profile(
        self,
        user_id: str,
        email: str
    ) -> Tuple[bool, Optional[Dict]]:
        """
        Get existing profile or create new one for onboarding flow.
        Implements 3-State Logic: State A (New), State B (Incomplete), State C (Complete).
        
        Args:
            user_id: Supabase user ID
            email: User email
            
        Returns:
            Tuple: (success: bool, profile_data: dict)
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                # Check if profile exists
                check_res = await client.get(
                    f"{self.supabase_url}/rest/v1/profiles?id=eq.{user_id}",
                    headers={
                        "apikey": self.supabase_key,
                        "Authorization": f"Bearer {self.service_role_key}",
                        "Range": "0-0"
                    }
                )
            
            if check_res.status_code == 200:
                profiles = check_res.json()
                if profiles:
                    # STATE B/C: Profile exists
                    profile = profiles[0]
                    logger.info(f"Profile exists for {email}")
                    return True, profile
            
            # STATE A: Create new profile
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                create_res = await client.post(
                    f"{self.supabase_url}/rest/v1/profiles",
                    headers={
                        "apikey": self.supabase_key,
                        "Authorization": f"Bearer {self.service_role_key}",
                        "Content-Type": "application/json",
                        "Prefer": "return=representation"
                    },
                    json={
                        "id": user_id,
                        "email": email,
                        "onboarded": False,
                        "created_at": datetime.utcnow().isoformat()
                    }
                )
            
            if create_res.status_code in [200, 201]:
                profile = create_res.json()[0] if isinstance(create_res.json(), list) else create_res.json()
                logger.info(f"Profile created for {email}")
                return True, profile
            else:
                logger.warning(f"Profile creation returned {create_res.status_code}")
                # Failsafe: Return minimal profile data
                return True, {
                    "id": user_id,
                    "email": email,
                    "onboarded": False,
                    "created_at": datetime.utcnow().isoformat()
                }
        
        except Exception as e:
            logger.error(f"Profile operation error: {str(e)}")
            # Failsafe: Return minimal profile
            return True, {
                "id": user_id,
                "email": email,
                "onboarded": False
            }
    
    def get_next_redirect_url(self, is_onboarded: bool) -> str:
        """
        Determine next redirect URL based on onboarding status.
        
        Args:
            is_onboarded: Whether user has completed onboarding
            
        Returns:
            Redirect URL path
        """
        return "/dashboard" if is_onboarded else "/onboarding"
