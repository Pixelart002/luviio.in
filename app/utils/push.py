"""
Push Notification Utility — Web Push API (VAPID)
=================================================
Uses pywebpush — free, no third-party service needed.
Works on Chrome, Firefox, Edge, Android Chrome.

Setup (one time):
  pip install pywebpush
  python -c "from py_vapid import Vapid; v=Vapid(); v.generate_keys(); print(v.public_key, v.private_key)"
  → Copy keys to env vars

Env vars needed:
  VAPID_PUBLIC_KEY=...
  VAPID_PRIVATE_KEY=...
  VAPID_CLAIM_EMAIL=mailto:admin@yourdomain.com
"""
import os
import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

VAPID_PUBLIC_KEY    = os.environ.get("VAPID_PUBLIC_KEY", "")
VAPID_PRIVATE_KEY   = os.environ.get("VAPID_PRIVATE_KEY", "")
VAPID_CLAIM_EMAIL   = os.environ.get("VAPID_CLAIM_EMAIL", "mailto:admin@luviio.in")


# ── 1 function = 1 feature ────────────────────────────────────────────────────

def send_push(subscription: dict[str, Any], title: str, body: str,
              icon: str = "/icon-192.png", url: str = "/") -> bool:
    """
    Send a single push notification to one subscription.
    Returns True on success, False on failure.
    subscription = {endpoint, keys: {p256dh, auth}}
    """
    if not VAPID_PRIVATE_KEY or not VAPID_PUBLIC_KEY:
        logger.warning("VAPID keys not set — push skipped")
        return False
        
    try:
        from pywebpush import webpush, WebPushException
        
        payload = json.dumps({
            "title": title,
            "body":  body,
            "icon":  icon,
            "url":   url,
        })
        
        webpush(
            subscription_info=subscription,
            data=payload,
            vapid_private_key=VAPID_PRIVATE_KEY,
            vapid_claims={"sub": VAPID_CLAIM_EMAIL},
        )
        logger.info("✓ Push sent | endpoint=%s... title=%s",
                    subscription.get("endpoint", "")[:40], title)
        return True
        
    except Exception as e:
        # We can distinguish between network errors and expired subscriptions
        # If it's a WebPushException, it often has a response object
        if e.__class__.__name__ == 'WebPushException':
            if hasattr(e, 'response') and e.response and e.response.status_code in [404, 410]:
                logger.info("Subscription expired or invalid (404/410) | endpoint=%s...", subscription.get("endpoint", "")[:20])
                return False
        
        logger.error("✗ Push failed | %s", e)
        return False


def send_push_to_user(sb_admin, user_id: str, title: str, body: str,
                      icon: str = "/icon-192.png", url: str = "/") -> int:
    """
    Send push to ALL subscriptions of a user.
    Returns count of successful sends.
    """
    try:
        result = (
            sb_admin.table("push_subscriptions")
            .select("subscription_json")
            .eq("user_id", user_id)
            .execute()
        )
        
        # SAFE CHECK: Prevent NoneType crash
        if not result or not hasattr(result, "data") or not result.data:
            return 0

        sent = 0
        dead = []   # expired subscriptions to clean up
        
        for row in result.data:
            try:
                sub = json.loads(row["subscription_json"])
                ok  = send_push(sub, title, body, icon, url)
                if ok:
                    sent += 1
                else:
                    dead.append(sub.get("endpoint"))
            except json.JSONDecodeError:
                logger.error(f"Invalid subscription JSON found for user {user_id}")
                continue

        # Clean up dead subscriptions safely
        for endpoint in dead:
            if endpoint:
                try:
                    sb_admin.table("push_subscriptions").delete().eq("endpoint", endpoint).execute()
                    logger.info("Cleaned up dead subscription | endpoint=%s...", endpoint[:20])
                except Exception as del_err:
                    logger.warning("Failed to clean up dead subscription | endpoint=%s... | error=%s", endpoint[:20], del_err)

        return sent
    except Exception as e:
        logger.error("send_push_to_user failed | user=%s | %s", user_id, e)
        return 0


def broadcast_push_to_admins(sb_admin, title: str, body: str,
                              icon: str = "/icon-192.png", url: str = "/admin.html") -> int:
    """Send push to all admin users — for low stock, new orders etc."""
    try:
        admins = (
            sb_admin.table("users")
            .select("id")
            .eq("role", "admin")
            .eq("is_active", True)
            .execute()
        )
        
        # SAFE CHECK: Prevent NoneType crash
        if not admins or not hasattr(admins, "data") or not admins.data:
            logger.info("No active admins found for broadcast.")
            return 0
            
        total = 0
        for admin in admins.data:
            total += send_push_to_user(sb_admin, admin["id"], title, body, icon, url)
            
        return total
    except Exception as e:
        logger.error("broadcast_push_to_admins failed | %s", e)
        return 0