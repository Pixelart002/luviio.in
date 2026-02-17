from fastapi import Response
import os

IS_PROD = os.environ.get("VERCEL_ENV") == "production"

def set_login_cookies(response: Response, access: str, refresh: str, session_id: str):
    flags = {"httponly": True, "secure": IS_PROD, "samesite": "lax", "path": "/"}
    response.set_cookie("access_token", access, max_age=3600, **flags)
    response.set_cookie("refresh_token", refresh, max_age=2592000, **flags)
    response.set_cookie("session_id", session_id, max_age=2592000, **flags)

def clear_auth_cookies(response: Response):
    flags = {"path": "/", "httponly": True, "secure": IS_PROD, "samesite": "lax"}
    response.delete_cookie("access_token", **flags)
    response.delete_cookie("refresh_token", **flags)
    response.delete_cookie("session_id", **flags)