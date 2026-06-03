"""
Push Notification Utility — Web Push API (VAPID)
=================================================
Features:
  • Circuit Breaker (stops pinging dead/blocking endpoints)
  • Rate Limiter (respects Push Service limits)
  • Parallel Execution (ThreadPoolExecutor)
  • Automatic Dead Subscription Cleanup
  • Strict Supabase NoneType Safety (AttributeError prevention)
"""
import os
import json
import logging
import time
import threading
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import requests

logger = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────────────
VAPID_PUBLIC_KEY  = os.environ.get("VAPID_PUBLIC_KEY", "")
VAPID_PRIVATE_KEY = os.environ.get("VAPID_PRIVATE_KEY", "")
VAPID_CLAIM_EMAIL = os.environ.get("VAPID_CLAIM_EMAIL", "mailto:admin@luviio.in")

_PUSH_TIMEOUT_SEC = 10          
_MAX_RETRIES = 2                
_RETRY_DELAY_SEC = 1.5          
_MAX_WORKERS = 10               

_CIRCUIT_BREAKER_THRESHOLD = 5  
_CIRCUIT_BREAKER_RESET_SEC = 60 

_RATE_LIMIT_PER_ENDPOINT = 3    

# ══════════════════════════════════════════════════════════════════════════════
#  CIRCUIT BREAKER
# ══════════════════════════════════════════════════════════════════════════════

class CircuitBreaker:
    def __init__(self, threshold: int = _CIRCUIT_BREAKER_THRESHOLD, reset_sec: int = _CIRCUIT_BREAKER_RESET_SEC):
        self.threshold = threshold
        self.reset_sec = reset_sec
        self._failures: dict[str, int] = defaultdict(int)
        self._tripped_until: dict[str, float] = {}
        self._lock = threading.Lock()
    
    def is_open(self, key: str) -> bool:
        with self._lock:
            tripped_until = self._tripped_until.get(key, 0)
            if tripped_until > time.time():
                return True
            if tripped_until > 0:
                self._tripped_until.pop(key, None)
                self._failures.pop(key, None)
            return False
    
    def record_failure(self, key: str) -> None:
        with self._lock:
            self._failures[key] += 1
            if self._failures[key] >= self.threshold:
                self._tripped_until[key] = time.time() + self.reset_sec
                logger.warning(
                    "Circuit BREAKER TRIPPED | key=%s failures=%d reset_in=%ds",
                    key, self._failures[key], self.reset_sec
                )
    
    def record_success(self, key: str) -> None:
        with self._lock:
            self._failures.pop(key, None)
            self._tripped_until.pop(key, None)

_push_circuit_breaker = CircuitBreaker()
_push_rate_limiter: dict[str, list[float]] = defaultdict(list)
_rate_lock = threading.Lock()

# ══════════════════════════════════════════════════════════════════════════════
#  RATE LIMITER
# ══════════════════════════════════════════════════════════════════════════════

def _check_rate_limit(endpoint: str) -> bool:
    now = time.time()
    with _rate_lock:
        _push_rate_limiter[endpoint] = [
            t for t in _push_rate_limiter.get(endpoint, [])
            if now - t < 1.0
        ]
        if len(_push_rate_limiter[endpoint]) >= _RATE_LIMIT_PER_ENDPOINT:
            return False
        _push_rate_limiter[endpoint].append(now)
        return True

# ══════════════════════════════════════════════════════════════════════════════
#  HTTP SESSION
# ══════════════════════════════════════════════════════════════════════════════

def _make_session() -> requests.Session:
    session = requests.Session()
    adapter = requests.adapters.HTTPAdapter(
        max_retries=0,
        pool_connections=20,
        pool_maxsize=20,
    )
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session

# ══════════════════════════════════════════════════════════════════════════════
#  SINGLE PUSH
# ══════════════════════════════════════════════════════════════════════════════

def send_push(
    subscription: dict[str, Any],
    title: str,
    body: str,
    icon: str = "/icon-192.png",
    url: str = "/",
) -> bool:
    if not VAPID_PRIVATE_KEY or not VAPID_PUBLIC_KEY:
        return False
    
    try:
        from pywebpush import webpush, WebPushException
    except ImportError:
        logger.error("pywebpush not installed — pip install pywebpush")
        return False
    
    endpoint = subscription.get("endpoint", "")
    endpoint_short = endpoint[:50] if endpoint else "unknown"
    
    endpoint_key = endpoint.split("/")[-1][:20] if endpoint else "unknown"
    if _push_circuit_breaker.is_open(endpoint_key):
        logger.debug("Circuit open — skipping push | endpoint=%s…", endpoint_short)
        return False
    
    if not _check_rate_limit(endpoint_key):
        logger.debug("Rate limited — skipping push | endpoint=%s…", endpoint_short)
        return False
    
    payload = json.dumps({
        "title": title,
        "body": body,
        "icon": icon,
        "url": url,
        "timestamp": int(time.time()),
    })
    
    last_error = None
    
    for attempt in range(1, _MAX_RETRIES + 2):
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
            
            _push_circuit_breaker.record_success(endpoint_key)
            logger.debug("Push sent | attempt=%d endpoint=%s…", attempt, endpoint_short)
            return True
            
        except Exception as exc:
            last_error = exc
            exc_name = exc.__class__.__name__
            
            if exc_name == "WebPushException":
                try:
                    status_code = exc.response.status_code if hasattr(exc, "response") and exc.response else None
                    if status_code in (404, 410):
                        logger.info("Dead subscription | endpoint=%s… status=%d", endpoint_short, status_code)
                        return False 
                    if status_code == 429:
                        logger.warning("Rate limited by push service | endpoint=%s…", endpoint_short)
                        time.sleep(5) 
                        continue
                except Exception:
                    pass
            
            if attempt <= _MAX_RETRIES:
                delay = _RETRY_DELAY_SEC * (2 ** (attempt - 1))
                logger.warning(
                    "Push failed (attempt %d/%d) — retrying in %.1fs | %s… | %s",
                    attempt, _MAX_RETRIES + 1, delay, endpoint_short, exc
                )
                time.sleep(delay)
            else:
                logger.error(
                    "Push permanently failed | endpoint=%s… | %s",
                    endpoint_short, last_error
                )
                _push_circuit_breaker.record_failure(endpoint_key)
    
    return False

# ══════════════════════════════════════════════════════════════════════════════
#  USER PUSH (PARALLEL)
# ══════════════════════════════════════════════════════════════════════════════

def send_push_to_user(
    sb_admin: Any,
    user_id: str,
    *,
    title: str,
    body: str,
    icon: str = "/icon-192.png",
    url: str = "/",
) -> int:
    if not user_id:
        logger.warning("send_push_to_user: empty user_id")
        return 0
    
    try:
        result = (
            sb_admin.table("push_subscriptions")
            .select("subscription_json")
            .eq("user_id", user_id)
            .execute()
        )
        
        # [FIX] Safe data extraction
        rows = getattr(result, "data", None)
        if not rows:
            logger.debug("No subscriptions found | user=%s", user_id[:8])
            return 0
        
        subs: list[dict] = []
        for row in rows:
            try:
                sub = json.loads(row.get("subscription_json", "{}"))
                if sub.get("endpoint"):
                    subs.append(sub)
            except (json.JSONDecodeError, TypeError) as exc:
                logger.warning("Invalid subscription JSON | user=%s: %s", user_id[:8], exc)
        
        if not subs:
            return 0
        
        logger.info("Sending push to user | user=%s subs=%d title=%s", user_id[:8], len(subs), title)
        
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
                    ok = future.result(timeout=_PUSH_TIMEOUT_SEC + 5)
                    if ok:
                        sent += 1
                    else:
                        ep = sub.get("endpoint")
                        if ep:
                            dead_endpoints.append(ep)
                except Exception as exc:
                    logger.error("Push future error | user=%s: %s", user_id[:8], exc)
        
        if dead_endpoints:
            logger.info("Cleaning %d dead subscriptions | user=%s", len(dead_endpoints), user_id[:8])
            
            def _delete_dead(ep: str) -> None:
                try:
                    sb_admin.table("push_subscriptions").delete().eq("endpoint", ep).execute()
                    logger.debug("Cleaned dead sub | endpoint=%s…", ep[:30])
                except Exception as exc:
                    logger.warning("Dead sub cleanup failed: %s", exc)
            
            with ThreadPoolExecutor(max_workers=min(5, len(dead_endpoints))) as pool:
                list(pool.map(_delete_dead, dead_endpoints))
        
        logger.info("Push complete | user=%s sent=%d/%d dead=%d", user_id[:8], sent, len(subs), len(dead_endpoints))
        return sent
        
    except Exception as exc:
        logger.error("send_push_to_user failed | user=%s: %s", user_id[:8], exc, exc_info=True)
        return 0

# ══════════════════════════════════════════════════════════════════════════════
#  BROADCAST TO ADMINS
# ══════════════════════════════════════════════════════════════════════════════

def broadcast_push_to_admins(
    sb_admin: Any,
    *,
    title: str,
    body: str,
    icon: str = "/icon-192.png",
    url: str = "/admin.html",
) -> int:
    try:
        admins = (
            sb_admin.table("users")
            .select("id, email")
            .eq("role", "admin")
            .eq("is_active", True)
            .execute()
        )
        
        # [FIX] Safe data extraction
        admin_rows = getattr(admins, "data", None)
        if not admin_rows:
            logger.info("No active admins found for broadcast")
            return 0
        
        admin_ids = [a["id"] for a in admin_rows]
        logger.info("Broadcasting to %d admins | title=%s", len(admin_ids), title)
        
        total = 0
        for admin_id in admin_ids:
            sent = send_push_to_user(
                sb_admin, admin_id,
                title=title, body=body, icon=icon, url=url,
            )
            total += sent
        
        logger.info("Broadcast complete | admins=%d total_sent=%d", len(admin_ids), total)
        return total
        
    except Exception as exc:
        logger.error("broadcast_push_to_admins failed: %s", exc, exc_info=True)
        return 0

def is_push_configured() -> bool:
    return bool(VAPID_PUBLIC_KEY and VAPID_PRIVATE_KEY and VAPID_CLAIM_EMAIL)
