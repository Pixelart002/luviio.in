"""
Push Notification Utility — Web Push API (VAPID)
=================================================
Architecture Layer: External Integrations
Path: app/integrations/push/webpush_impl.py
"""
import asyncio
import hashlib
import json
import logging
import os
import random
import threading
import time
from collections import defaultdict
from typing import Any, Literal

import requests
from starlette.concurrency import run_in_threadpool

from app.core.supabase import get_async_admin_supabase

logger = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────────────
VAPID_PUBLIC_KEY = os.environ.get("VAPID_PUBLIC_KEY", "")
VAPID_PRIVATE_KEY = os.environ.get("VAPID_PRIVATE_KEY", "")
VAPID_CLAIM_EMAIL = os.environ.get("VAPID_CLAIM_EMAIL", "mailto:admin@luviio.in")

_PUSH_TIMEOUT_SEC = 10
_MAX_RETRIES = 2
_RETRY_DELAY_SEC = 1.5
_MAX_RETRY_DELAY_SEC = 10.0
_CIRCUIT_BREAKER_THRESHOLD = 5
_CIRCUIT_BREAKER_RESET_SEC = 60
_RATE_LIMIT_PER_ENDPOINT = 3

PushResult = Literal["sent", "dead", "failed"]


class CircuitBreaker:
    def __init__(
        self,
        threshold: int = _CIRCUIT_BREAKER_THRESHOLD,
        reset_sec: int = _CIRCUIT_BREAKER_RESET_SEC,
    ):
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
        _push_rate_limiter[endpoint] = [
            timestamp
            for timestamp in _push_rate_limiter.get(endpoint, [])
            if now - timestamp < 1.0
        ]
        if len(_push_rate_limiter[endpoint]) >= _RATE_LIMIT_PER_ENDPOINT:
            return False
        _push_rate_limiter[endpoint].append(now)
        return True


def _endpoint_key(endpoint: str) -> str:
    """Return a stable non-sensitive key for circuit/rate-limit state."""
    return hashlib.sha256(endpoint.encode("utf-8")).hexdigest()[:20]


def _retry_after_seconds(exc: Exception) -> float | None:
    response = getattr(exc, "response", None)
    value = response.headers.get("Retry-After") if response is not None else None
    if value is None:
        return None
    try:
        return max(0.0, min(float(value), _MAX_RETRY_DELAY_SEC))
    except (TypeError, ValueError):
        return None


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


def send_push(
    subscription: dict[str, Any],
    title: str,
    body: str,
    icon: str = "/icon-192.png",
    url: str = "/",
) -> PushResult:
    """Send one push and classify the result for safe subscription cleanup."""
    if not VAPID_PRIVATE_KEY or not VAPID_PUBLIC_KEY:
        logger.warning("Web push is not configured")
        return "failed"

    try:
        from pywebpush import WebPushException, webpush
    except ImportError:
        logger.exception("pywebpush dependency is unavailable")
        return "failed"

    endpoint = subscription.get("endpoint", "")
    if not endpoint:
        logger.warning("Web push subscription has no endpoint")
        return "dead"

    endpoint_key = _endpoint_key(endpoint)
    if _push_circuit_breaker.is_open(endpoint_key):
        return "failed"
    if not _check_rate_limit(endpoint_key):
        return "failed"

    payload = json.dumps(
        {
            "title": title,
            "body": body,
            "icon": icon,
            "url": url,
            "timestamp": int(time.time()),
        }
    )

    session = _make_session()
    try:
        for attempt in range(1, _MAX_RETRIES + 2):
            try:
                webpush(
                    subscription_info=subscription,
                    data=payload,
                    vapid_private_key=VAPID_PRIVATE_KEY,
                    vapid_claims={"sub": VAPID_CLAIM_EMAIL},
                    requests_session=session,
                    timeout=_PUSH_TIMEOUT_SEC,
                )
                _push_circuit_breaker.record_success(endpoint_key)
                return "sent"
            except WebPushException as exc:
                response = getattr(exc, "response", None)
                status_code = getattr(response, "status_code", None)

                if status_code in (404, 410):
                    logger.info(
                        "Web push subscription expired",
                        extra={"endpoint_key": endpoint_key, "status_code": status_code},
                    )
                    return "dead"

                if status_code == 429 and attempt <= _MAX_RETRIES:
                    delay = _retry_after_seconds(exc)
                    if delay is None:
                        delay = min(
                            _RETRY_DELAY_SEC * (2 ** (attempt - 1))
                            + random.uniform(0, 0.5),
                            _MAX_RETRY_DELAY_SEC,
                        )
                    time.sleep(delay)
                    continue

                if attempt <= _MAX_RETRIES:
                    delay = min(
                        _RETRY_DELAY_SEC * (2 ** (attempt - 1))
                        + random.uniform(0, 0.5),
                        _MAX_RETRY_DELAY_SEC,
                    )
                    time.sleep(delay)
                    continue

                _push_circuit_breaker.record_failure(endpoint_key)
                logger.warning(
                    "Web push delivery failed",
                    extra={"endpoint_key": endpoint_key, "status_code": status_code},
                )
                return "failed"
            except requests.RequestException as exc:
                if attempt <= _MAX_RETRIES:
                    delay = min(
                        _RETRY_DELAY_SEC * (2 ** (attempt - 1))
                        + random.uniform(0, 0.5),
                        _MAX_RETRY_DELAY_SEC,
                    )
                    time.sleep(delay)
                    continue

                _push_circuit_breaker.record_failure(endpoint_key)
                logger.warning(
                    "Web push network request failed",
                    extra={"endpoint_key": endpoint_key, "error_type": type(exc).__name__},
                )
                return "failed"
            except (ValueError, TypeError, KeyError) as exc:
                logger.warning(
                    "Web push subscription data is invalid",
                    extra={"endpoint_key": endpoint_key, "error_type": type(exc).__name__},
                )
                return "failed"
            except Exception:
                _push_circuit_breaker.record_failure(endpoint_key)
                logger.exception(
                    "Unexpected web push delivery failure",
                    extra={"endpoint_key": endpoint_key},
                )
                return "failed"
    finally:
        session.close()

    return "failed"


async def send_push_to_user(
    user_id: str,
    *,
    title: str,
    body: str,
    icon: str = "/icon-192.png",
    url: str = "/",
) -> int:
    if not user_id:
        return 0
    try:
        sb_admin = await get_async_admin_supabase()
        result = (
            await sb_admin.table("push_subscriptions")
            .select("subscription_json")
            .eq("user_id", user_id)
            .execute()
        )
        rows = getattr(result, "data", None)
        if not rows:
            return 0

        subs: list[dict[str, Any]] = []
        for row in rows:
            try:
                sub = json.loads(row.get("subscription_json", "{}"))
                if sub.get("endpoint"):
                    subs.append(sub)
            except (json.JSONDecodeError, TypeError, AttributeError):
                logger.warning("Ignoring malformed stored push subscription")

        if not subs:
            return 0

        tasks = [
            run_in_threadpool(send_push, sub, title, body, icon, url)
            for sub in subs
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        sent = 0
        dead_endpoints: list[str] = []

        for sub, result in zip(subs, results):
            if result == "sent":
                sent += 1
            elif result == "dead":
                endpoint = sub.get("endpoint")
                if endpoint:
                    dead_endpoints.append(endpoint)
            elif isinstance(result, Exception):
                logger.warning(
                    "Push worker failed",
                    extra={"error_type": type(result).__name__},
                )

        if dead_endpoints:
            delete_tasks = [
                sb_admin.table("push_subscriptions").delete().eq("endpoint", endpoint).execute()
                for endpoint in dead_endpoints
            ]
            delete_results = await asyncio.gather(*delete_tasks, return_exceptions=True)
            for result in delete_results:
                if isinstance(result, Exception):
                    logger.warning(
                        "Failed to remove expired push subscription",
                        extra={"error_type": type(result).__name__},
                    )

        return sent
    except Exception:
        logger.exception("Push processing failed")
        return 0


async def broadcast_push_to_admins(
    *,
    title: str,
    body: str,
    icon: str = "/icon-192.png",
    url: str = "/admin.html",
) -> int:
    try:
        sb_admin = await get_async_admin_supabase()
        admins = (
            await sb_admin.table("users")
            .select("id")
            .eq("role", "admin")
            .eq("is_active", True)
            .execute()
        )
        admin_rows = getattr(admins, "data", None)
        if not admin_rows:
            return 0

        tasks = [
            send_push_to_user(a["id"], title=title, body=body, icon=icon, url=url)
            for a in admin_rows
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        return sum(result for result in results if isinstance(result, int))
    except Exception:
        logger.exception("Admin broadcast failed")
        return 0


def is_push_configured() -> bool:
    return bool(VAPID_PUBLIC_KEY and VAPID_PRIVATE_KEY and VAPID_CLAIM_EMAIL)
