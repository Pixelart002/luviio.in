"""
Push Notification Utility — Web Push API (VAPID)
=================================================
Architecture Layer: External Integrations
Path: app/integrations/push/webpush_impl.py
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
            if tripped_until > time.time(): return True
            if tripped_until > 0:
                self._tripped_until.pop(key, None)
                self._failures.pop(key, None)
            return False
    
    def record_failure(self, key: str) -> None:
        with self._lock:
            self._failures[key] += 1
            if self._failures[key] >= self.threshold:
                self._tripped_until[key] = time.time() + self.reset_sec
    
    def record_success(self, key: str) -> None:
        with self._lock:
            self._failures.pop(key, None)
            self._tripped_until.pop(key, None)

_push_circuit_breaker = CircuitBreaker()
_push_rate_limiter: dict[str, list[float]] = defaultdict(list)
_rate_lock = threading.Lock()

def _check_rate_limit(endpoint: str) -> bool:
    now = time.time()
    with _rate_lock:
        _push_rate_limiter[endpoint] = [t for t in _push_rate_limiter.get(endpoint, []) if now - t < 1.0]
        if len(_push_rate_limiter[endpoint]) >= _RATE_LIMIT_PER_ENDPOINT: return False
        _push_rate_limiter[endpoint].append(now)
        return True

def _make_session() -> requests.Session:
    session = requests.Session()
    adapter = requests.adapters.HTTPAdapter(max_retries=0, pool_connections=20, pool_maxsize=20)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session

def send_push(subscription: dict[str, Any], title: str, body: str, icon: str = "/icon-192.png", url: str = "/") -> bool:
    if not VAPID_PRIVATE_KEY or not VAPID_PUBLIC_KEY: return False
    try: from pywebpush import webpush, WebPushException
    except ImportError: return False
    
    endpoint = subscription.get("endpoint", "")
    endpoint_key = endpoint.split("/")[-1][:20] if endpoint else "unknown"
    if _push_circuit_breaker.is_open(endpoint_key): return False
    if not _check_rate_limit(endpoint_key): return False
    
    payload = json.dumps({"title": title, "body": body, "icon": icon, "url": url, "timestamp": int(time.time())})
    last_error = None
    
    for attempt in range(1, _MAX_RETRIES + 2):
        try:
            session = _make_session()
            webpush(
                subscription_info=subscription, data=payload, vapid_private_key=VAPID_PRIVATE_KEY,
                vapid_claims={"sub": VAPID_CLAIM_EMAIL}, requests_session=session, timeout=_PUSH_TIMEOUT_SEC,
            )
            _push_circuit_breaker.record_success(endpoint_key)
            return True
        except Exception as exc:
            last_error = exc
            exc_name = exc.__class__.__name__
            if exc_name == "WebPushException":
                try:
                    status_code = exc.response.status_code if hasattr(exc, "response") and exc.response else None
                    if status_code is None:
                        import re as _re
                        _m = _re.search(r"\b(4\d{2}|5\d{2})\b", str(exc))
                        if _m: status_code = int(_m.group(1))
                    if status_code in (404, 410): return False
                    if status_code == 429:
                        time.sleep(5) 
                        continue
                except Exception: pass
            
            if attempt <= _MAX_RETRIES:
                time.sleep(_RETRY_DELAY_SEC * (2 ** (attempt - 1)))
            else:
                _push_circuit_breaker.record_failure(endpoint_key)
    return False

def send_push_to_user(sb_admin: Any, user_id: str, *, title: str, body: str, icon: str = "/icon-192.png", url: str = "/") -> int:
    if not user_id: return 0
    try:
        result = sb_admin.table("push_subscriptions").select("subscription_json").eq("user_id", user_id).execute()
        rows = getattr(result, "data", None)
        if not rows: return 0
        
        subs: list[dict] = []
        for row in rows:
            try:
                sub = json.loads(row.get("subscription_json", "{}"))
                if sub.get("endpoint"): subs.append(sub)
            except (json.JSONDecodeError, TypeError): pass
        
        if not subs: return 0
        sent = 0
        dead_endpoints: list[str] = []
        
        with ThreadPoolExecutor(max_workers=min(_MAX_WORKERS, len(subs))) as pool:
            future_to_sub = {pool.submit(send_push, sub, title, body, icon, url): sub for sub in subs}
            for future in as_completed(future_to_sub):
                sub = future_to_sub[future]
                try:
                    if future.result(timeout=_PUSH_TIMEOUT_SEC + 5): sent += 1
                    else:
                        ep = sub.get("endpoint")
                        if ep: dead_endpoints.append(ep)
                except Exception: pass
        
        if dead_endpoints:
            def _delete_dead(ep: str) -> None:
                try: sb_admin.table("push_subscriptions").delete().eq("endpoint", ep).execute()
                except Exception: pass
            with ThreadPoolExecutor(max_workers=min(5, len(dead_endpoints))) as pool:
                list(pool.map(_delete_dead, dead_endpoints))
        
        return sent
    except Exception as exc: return 0

def broadcast_push_to_admins(sb_admin: Any, *, title: str, body: str, icon: str = "/icon-192.png", url: str = "/admin.html") -> int:
    try:
        admins = sb_admin.table("users").select("id, email").eq("role", "admin").eq("is_active", True).execute()
        admin_rows = getattr(admins, "data", None)
        if not admin_rows: return 0
        
        admin_ids = [a["id"] for a in admin_rows]
        total = 0
        for admin_id in admin_ids:
            total += send_push_to_user(sb_admin, admin_id, title=title, body=body, icon=icon, url=url)
        return total
    except Exception as exc: return 0

def is_push_configured() -> bool:
    return bool(VAPID_PUBLIC_KEY and VAPID_PRIVATE_KEY and VAPID_CLAIM_EMAIL)