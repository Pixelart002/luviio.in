"""
Push Notification Utility — FIXED with detailed logging
"""
import os, json, logging
from typing import Any

logger = logging.getLogger(__name__)

VAPID_PUBLIC_KEY  = os.environ.get("VAPID_PUBLIC_KEY", "")
VAPID_PRIVATE_KEY = os.environ.get("VAPID_PRIVATE_KEY", "")
VAPID_CLAIM_EMAIL = os.environ.get("VAPID_CLAIM_EMAIL", "mailto:admin@luviio.in")


def _check_vapid() -> bool:
    if not VAPID_PRIVATE_KEY:
        logger.error("[PUSH] VAPID_PRIVATE_KEY not set — add it to Koyeb env vars")
        return False
    if not VAPID_PUBLIC_KEY:
        logger.error("[PUSH] VAPID_PUBLIC_KEY not set — add it to Koyeb env vars")
        return False
    return True


def send_push(subscription: dict[str, Any], title: str, body: str,
              icon: str = "/icon-192.png", url: str = "/") -> bool:
    if not _check_vapid():
        return False
    endpoint = subscription.get("endpoint", "")
    if not endpoint:
        logger.error("[PUSH] subscription has no endpoint — skipping")
        return False
    try:
        from pywebpush import webpush, WebPushException
    except ImportError:
        logger.error("[PUSH] pywebpush not installed — pip install pywebpush==2.0.0")
        return False
    payload = json.dumps({"title": title, "body": body, "icon": icon, "url": url})
    try:
        webpush(
            subscription_info=subscription,
            data=payload,
            vapid_private_key=VAPID_PRIVATE_KEY,
            vapid_claims={"sub": VAPID_CLAIM_EMAIL},
        )
        logger.info("[PUSH] Sent OK | title=%r endpoint=%.40s", title, endpoint)
        return True
    except Exception as exc:
        s = str(exc)
        if "410" in s:
            logger.warning("[PUSH] Subscription expired (410) | endpoint=%.40s", endpoint)
        elif "403" in s:
            logger.error("[PUSH] 403 — VAPID key mismatch, user needs to re-subscribe")
        elif "401" in s:
            logger.error("[PUSH] 401 — VAPID_CLAIM_EMAIL or private key wrong")
        else:
            logger.error("[PUSH] Failed: %s | endpoint=%.40s", exc, endpoint)
        return False


def send_push_to_user(sb_admin, user_id: str, title: str, body: str,
                      icon: str = "/icon-192.png", url: str = "/") -> int:
    if not user_id:
        logger.error("[PUSH] send_push_to_user called with empty user_id")
        return 0
    try:
        result = (
            sb_admin.table("push_subscriptions")
            .select("subscription_json, endpoint")
            .eq("user_id", user_id)
            .execute()
        )
        if not result.data:
            logger.warning("[PUSH] No subscription for user=%s — user needs to allow notifications", user_id[:8])
            return 0
        logger.info("[PUSH] %d subscription(s) found for user=%s", len(result.data), user_id[:8])
        sent = 0
        dead = []
        for row in result.data:
            try:
                sub = json.loads(row["subscription_json"])
            except Exception as e:
                logger.error("[PUSH] Bad subscription JSON user=%s: %s", user_id[:8], e)
                continue
            ok = send_push(sub, title, body, icon, url)
            if ok:
                sent += 1
            else:
                ep = sub.get("endpoint", "")
                if ep:
                    dead.append(ep)
        for ep in dead:
            try:
                sb_admin.table("push_subscriptions").delete().eq("endpoint", ep).execute()
                logger.info("[PUSH] Cleaned expired sub | endpoint=%.40s", ep)
            except Exception:
                pass
        logger.info("[PUSH] Delivered %d/%d to user=%s", sent, len(result.data), user_id[:8])
        return sent
    except Exception as e:
        logger.error("[PUSH] send_push_to_user error user=%s: %s", user_id[:8], e, exc_info=True)
        return 0


def broadcast_push_to_admins(sb_admin, title: str, body: str,
                              icon: str = "/icon-192.png", url: str = "/admin.html") -> int:
    try:
        admins = (
            sb_admin.table("users")
            .select("id, email")
            .eq("role", "admin")
            .eq("is_active", True)
            .execute()
        )
        if not admins.data:
            logger.warning("[PUSH] No admin users in DB")
            return 0
        logger.info("[PUSH] Broadcasting to %d admin(s)", len(admins.data))
        total = 0
        for admin in admins.data:
            count = send_push_to_user(sb_admin, admin["id"], title, body, icon, url)
            if count == 0:
                logger.warning(
                    "[PUSH] Admin %s (%s) has no subscription — "
                    "open luviio.in and allow notifications in browser",
                    admin["id"][:8], admin.get("email", "?")
                )
            total += count
        logger.info("[PUSH] Broadcast complete | delivered=%d", total)
        return total
    except Exception as e:
        logger.error("[PUSH] broadcast_push_to_admins error: %s", e, exc_info=True)
        return 0