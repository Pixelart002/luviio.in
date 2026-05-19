"""
Push Notification Utility — Web Push API (VAPID)
=================================================
FIXES:
  1. Parallel sending — ThreadPoolExecutor se sab subscriptions ek saath
  2. Timeout — webpush() ab 10s mein timeout hoga, hang nahi karega
  3. Retry — transient failures pe 2 baar retry (exponential backoff)
  4. Dead subscription cleanup bhi parallel
"""
import os
import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import requests

logger = logging.getLogger(__name__)

VAPID_PUBLIC_KEY  = os.environ.get("VAPID_PUBLIC_KEY", "")
VAPID_PRIVATE_KEY = os.environ.get("VAPID_PRIVATE_KEY", "")
VAPID_CLAIM_EMAIL = os.environ.get("VAPID_CLAIM_EMAIL", "mailto:admin@luviio.in")

_PUSH_TIMEOUT_SEC = 10      # webpush() HTTP timeout
_MAX_RETRIES      = 2       # transient failure pe retry attempts
_RETRY_DELAY_SEC  = 1.5     # first retry delay (doubles on second)
_MAX_WORKERS      = 10      # parallel push threads


def _make_session() -> requests.Session:
    """Timeout-aware requests session for pywebpush."""
    session = requests.Session()
    adapter = requests.adapters.HTTPAdapter(max_retries=0)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def send_push(
    subscription: dict[str, Any],
    title: str,
    body: str,
    icon: str = "/icon-192.png",
    url: str = "/",
) -> bool:
    """
    Single subscription ko push bhejo.
    Timeout + retry included.
    Returns True on success, False on permanent failure.
    """
    if not VAPID_PRIVATE_KEY or not VAPID_PUBLIC_KEY:
        logger.warning("VAPID keys not set — push skipped")
        return False

    try:
        from pywebpush import webpush, WebPushException
    except ImportError:
        logger.error("pywebpush not installed — pip install pywebpush")
        return False

    payload = json.dumps({"title": title, "body": body, "icon": icon, "url": url})
    endpoint = subscription.get("endpoint", "")[:40]

    for attempt in range(1, _MAX_RETRIES + 2):  # 1, 2, 3
        try:
            session = _make_session()
            webpush(
                subscription_info=subscription,
                data=payload,
                vapid_private_key=VAPID_PRIVATE_KEY,
                vapid_claims={"sub": VAPID_CLAIM_EMAIL},
                requests_session=session,
                timeout=_PUSH_TIMEOUT_SEC,
            )
            logger.info("Push sent | attempt=%d endpoint=%s… title=%s",
                        attempt, endpoint, title)
            return True

        except Exception as e:
            # 404/410 = subscription expired — no retry needed
            is_wpex = e.__class__.__name__ == "WebPushException"
            if is_wpex and hasattr(e, "response") and e.response:
                if e.response.status_code in (404, 410):
                    logger.info("Subscription expired (404/410) | endpoint=%s…", endpoint)
                    return False  # dead subscription

            if attempt <= _MAX_RETRIES:
                delay = _RETRY_DELAY_SEC * (2 ** (attempt - 1))
                logger.warning(
                    "Push failed (attempt %d/%d) — retrying in %.1fs | %s",
                    attempt, _MAX_RETRIES + 1, delay, e,
                )
                time.sleep(delay)
            else:
                logger.error("Push failed permanently | endpoint=%s… | %s", endpoint, e)
                return False

    return False


def send_push_to_user(
    sb_admin: Any,
    user_id: str,
    *,
    title: str,
    body: str,
    icon: str = "/icon-192.png",
    url: str = "/",
) -> int:
    """
    User ke SAARE subscriptions ko PARALLEL mein push bhejo.
    Returns count of successful sends.
    """
    try:
        result = (
            sb_admin.table("push_subscriptions")
            .select("subscription_json")
            .eq("user_id", user_id)
            .execute()
        )
        if not result or not result.data:
            return 0

        subs: list[dict] = []
        for row in result.data:
            try:
                subs.append(json.loads(row["subscription_json"]))
            except json.JSONDecodeError:
                logger.error("Invalid subscription JSON | user=%s", user_id)

        if not subs:
            return 0

        # ── Parallel send ─────────────────────────────────────────────────────
        sent = 0
        dead_endpoints: list[str] = []

        with ThreadPoolExecutor(max_workers=min(_MAX_WORKERS, len(subs))) as pool:
            future_to_sub = {
                pool.submit(send_push, sub, title, body, icon, url): sub
                for sub in subs
            }
            for future in as_completed(future_to_sub):
                sub = future_to_sub[future]
                try:
                    ok = future.result()
                    if ok:
                        sent += 1
                    else:
                        ep = sub.get("endpoint")
                        if ep:
                            dead_endpoints.append(ep)
                except Exception as e:
                    logger.error("Push future error | user=%s | %s", user_id, e)

        # ── Parallel cleanup of dead subscriptions ────────────────────────────
        if dead_endpoints:
            def _delete(ep: str) -> None:
                try:
                    sb_admin.table("push_subscriptions").delete().eq("endpoint", ep).execute()
                    logger.info("Cleaned dead subscription | endpoint=%s…", ep[:20])
                except Exception as del_err:
                    logger.warning("Dead sub cleanup failed | %s", del_err)

            with ThreadPoolExecutor(max_workers=min(5, len(dead_endpoints))) as pool:
                list(pool.map(_delete, dead_endpoints))

        return sent

    except Exception as e:
        logger.error("send_push_to_user failed | user=%s | %s", user_id, e)
        return 0


def broadcast_push_to_admins(
    sb_admin: Any,
    *,
    title: str,
    body: str,
    icon: str = "/icon-192.png",
    url: str = "/admin.html",
) -> int:
    """Saare active admins ko push bhejo."""
    try:
        admins = (
            sb_admin.table("users")
            .select("id")
            .eq("role", "admin")
            .eq("is_active", True)
            .execute()
        )
        if not admins or not admins.data:
            logger.info("No active admins found for broadcast.")
            return 0

        total = 0
        for admin in admins.data:
            total += send_push_to_user(
                sb_admin, admin["id"],
                title=title, body=body, icon=icon, url=url,
            )
        return total

    except Exception as e:
        logger.error("broadcast_push_to_admins failed | %s", e)
        return 0
