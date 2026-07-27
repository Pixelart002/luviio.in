"""
Auth Policies & Brute Force Guard
=================================
Path: app/permissions/policies/auth_policies.py
"""
import time
import logging
from typing import Dict, List
from fastapi import HTTPException, status
from app.constants.auth_messages import AuthSecurityMessages, AuthRules

logger = logging.getLogger(__name__)

# In-memory brute force protection state
_login_attempts: Dict[str, List[float]] = {}
_blocked_ips: Dict[str, float] = {}

class AuthPolicy:

    @staticmethod
    def assert_safe_attempt(ip: str, email: str = "") -> None:
        """ABAC Guard: Prevents credential stuffing and brute-force attacks."""
        now = time.time()
        global _login_attempts, _blocked_ips
        
        # Cleanup expired attempts & blocks
        _login_attempts = {k: [t for t in v if now - t < AuthRules.LOGIN_WINDOW_SECONDS] for k, v in _login_attempts.items()}
        _login_attempts = {k: v for k, v in _login_attempts.items() if v}
        _blocked_ips = {k: v for k, v in _blocked_ips.items() if v > now}
        
        if ip in _blocked_ips: 
            logger.warning("Auth Block | Blocked IP attempted access: %s", ip)
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=AuthSecurityMessages.TOO_MANY_REQUESTS)
            
        email_key = f"email:{email}" if email else None
        if email_key and email_key in _blocked_ips: 
            logger.warning("Auth Block | Blocked Email attempted access: %s", email)
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=AuthSecurityMessages.TOO_MANY_REQUESTS)
        
        ip_attempts = len(_login_attempts.get(ip, []))
        email_attempts = len(_login_attempts.get(email_key, [])) if email_key else 0
        
        if ip_attempts >= AuthRules.MAX_LOGIN_ATTEMPTS or email_attempts >= AuthRules.MAX_LOGIN_ATTEMPTS:
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=AuthSecurityMessages.TOO_MANY_REQUESTS)

    @staticmethod
    def record_failed_attempt(ip: str, email: str = "") -> None:
        """Records a failed attempt and blocks if threshold is breached."""
        now = time.time()
        _login_attempts.setdefault(ip, []).append(now)
        if email: _login_attempts.setdefault(f"email:{email}", []).append(now)
        
        if len(_login_attempts[ip]) >= AuthRules.MAX_LOGIN_ATTEMPTS:
            _blocked_ips[ip] = now + AuthRules.LOGIN_COOLDOWN_SECONDS
            logger.warning("Auth Alert | IP %s blocked for brute force.", ip)
            
        if email:
            email_key = f"email:{email}"
            if len(_login_attempts.get(email_key, [])) >= AuthRules.MAX_LOGIN_ATTEMPTS:
                _blocked_ips[email_key] = now + AuthRules.LOGIN_COOLDOWN_SECONDS
                logger.warning("Auth Alert | Email %s blocked for brute force.", email)

    @staticmethod
    def reset_attempts(ip: str, email: str = "") -> None:
        """Clears records on successful authentication."""
        _login_attempts.pop(ip, None)
        _blocked_ips.pop(ip, None)
        if email:
            _login_attempts.pop(f"email:{email}", None)
            _blocked_ips.pop(f"email:{email}", None)