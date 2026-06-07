"""
Security Middlewares — Production Grade (with GZip)
=====================================================
ASGI middlewares for performance, security, and server hardening.

Middleware Stack (Order Matters!):
  1. RequestIDMiddleware       → Unique ID for every request (tracing)
  2. MaxBodySizeMiddleware     → Reject oversized request bodies (anti-DoS)
  3. GZipMiddleware            → Compress JSON responses (performance)
  4. HideServerHeaderMiddleware → Mask server signature (fingerprinting)
  5. SecurityHeadersMiddleware  → Security-focused HTTP headers

FIXES APPLIED:
  1. GZipMiddleware: Fixed RAM Memory Leak (OOM) on Streaming Responses.
  2. MaxBodySizeMiddleware: Blocked Chunked-Encoding bypass attacks.
"""
import gzip
import io
import uuid
import logging

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════════
#  1. REQUEST ID MIDDLEWARE
# ══════════════════════════════════════════════════════════════════════════════

class RequestIDMiddleware:
    """
    Assigns a unique 8-char ID to every request for tracing.
    """

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = str(uuid.uuid4())[:8]

        # Add to request scope
        existing_headers = list(scope.get("headers", []))
        existing_headers.append((b"x-request-id", request_id.encode()))
        scope = {**scope, "headers": existing_headers}

        async def send_with_id(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                if not any(k.lower() == b"x-request-id" for k, _ in headers):
                    headers.append((b"x-request-id", request_id.encode()))
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_with_id)


# ══════════════════════════════════════════════════════════════════════════════
#  2. MAX BODY SIZE MIDDLEWARE
# ══════════════════════════════════════════════════════════════════════════════

class MaxBodySizeMiddleware:
    """
    Rejects requests with body larger than max_bytes.
    Prevents memory exhaustion from oversized uploads.
    """

    def __init__(self, app, max_bytes: int = 10 * 1024 * 1024) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        if scope.get("method") == "OPTIONS":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))
        content_length_raw = headers.get(b"content-length")

        # 1. Fast check if Content-Length header is present
        if content_length_raw:
            try:
                content_length = int(content_length_raw)
                if content_length > self.max_bytes:
                    await self._send_413(send, scope.get("path", "?"), content_length)
                    return
            except ValueError:
                pass

        # 2. Deep check for Chunked-Encoding bypass
        total_bytes = 0

        async def receive_wrapper():
            nonlocal total_bytes
            message = await receive()
            if message["type"] == "http.request":
                total_bytes += len(message.get("body", b""))
                if total_bytes > self.max_bytes:
                    # Abort reading to save memory
                    raise RuntimeError("Request body exceeded maximum size limit")
            return message

        try:
            await self.app(scope, receive_wrapper, send)
        except RuntimeError as e:
            if "maximum size limit" in str(e):
                await self._send_413(send, scope.get("path", "?"), total_bytes)
            else:
                raise

    async def _send_413(self, send, path, size):
        logger.warning(
            "Body too large | size=%d max=%d path=%s",
            size, self.max_bytes, path
        )
        response = b'{"detail":"Request body too large","max_bytes":%d}' % self.max_bytes
        await send({
            "type": "http.response.start",
            "status": 413,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(response)).encode()),
                (b"connection", b"close"),
            ],
        })
        await send({"type": "http.response.body", "body": response})


# ══════════════════════════════════════════════════════════════════════════════
#  3. GZIP COMPRESSION MIDDLEWARE
# ══════════════════════════════════════════════════════════════════════════════

class GZipMiddleware:
    """
    Compresses JSON/text responses to reduce bandwidth.
    """

    _COMPRESSIBLE = {
        "application/json", "application/javascript", "application/xml",
        "text/html", "text/css", "text/plain", "text/javascript", "text/xml",
    }
    _ALREADY_COMPRESSED = {
        "image/png", "image/jpeg", "image/webp", "image/gif",
        "image/svg+xml", "video/mp4", "video/webm",
        "audio/mpeg", "audio/ogg", "application/zip",
        "application/pdf", "application/gzip", "application/octet-stream",
    }

    def __init__(self, app, min_size: int = 500, compression_level: int = 6):
        self.app = app
        self.min_size = min_size
        self.compression_level = compression_level

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        req_headers = dict(scope.get("headers", []))
        accept_encoding = req_headers.get(b"accept-encoding", b"").decode("latin-1", errors="ignore").lower()

        if "gzip" not in accept_encoding:
            await self.app(scope, receive, send)
            return

        response_status = 200
        response_headers = []
        content_type = ""
        started = False

        async def intercept_send(message):
            nonlocal response_status, response_headers, content_type, started

            if message["type"] == "http.response.start":
                response_status = message.get("status", 200)
                response_headers = list(message.get("headers", []))

                for k, v in response_headers:
                    if k.lower() == b"content-type":
                        content_type = v.decode("latin-1", errors="ignore").split(";")[0].strip().lower()

            elif message["type"] == "http.response.body":
                if not started:
                    # [FIX] RAM Memory Leak protection for StreamingResponses
                    if message.get("more_body", False):
                        # This is a stream. Buffering will cause OOM. Send uncompressed instantly.
                        await send({
                            "type": "http.response.start", "status": response_status,
                            "headers": response_headers,
                        })
                        await send(message)
                        started = True
                    else:
                        # Single complete chunk — safe to buffer and compress
                        body = message.get("body", b"")
                        await self._send_compressed(send, response_status, response_headers, body, content_type)
                        started = True
                else:
                    # Already streaming fallback, just pass the chunks through
                    await send(message)

        await self.app(scope, receive, intercept_send)

    async def _send_compressed(self, send, status, headers, body, content_type):
        """Compress if applicable, otherwise send as-is."""
        if not self._should_compress(body, content_type):
            await send({
                "type": "http.response.start", "status": status,
                "headers": headers,
            })
            await send({"type": "http.response.body", "body": body})
            return

        try:
            original_size = len(body)
            buf = io.BytesIO()
            with gzip.GzipFile(fileobj=buf, mode="wb", compresslevel=self.compression_level) as gz:
                gz.write(body)
            compressed = buf.getvalue()
            compressed_size = len(compressed)

            final_headers = [
                (k, v) for k, v in headers
                if k.lower() not in (b"content-length", b"content-encoding")
            ]
            final_headers.append((b"content-encoding", b"gzip"))
            final_headers.append((b"content-length", str(compressed_size).encode()))
            final_headers.append((b"vary", b"Accept-Encoding"))

            await send({
                "type": "http.response.start", "status": status,
                "headers": final_headers,
            })
            await send({"type": "http.response.body", "body": compressed})

            ratio = (1 - compressed_size / original_size) * 100 if original_size > 0 else 0
            logger.debug(
                "GZip: %d→%d bytes (%.1f%%) | type=%s",
                original_size, compressed_size, ratio, content_type
            )

        except Exception as exc:
            logger.error("GZip failed — sending uncompressed: %s", exc)
            await send({
                "type": "http.response.start", "status": status,
                "headers": headers,
            })
            await send({"type": "http.response.body", "body": body})

    def _should_compress(self, body: bytes, content_type: str) -> bool:
        if len(body) < self.min_size:
            return False
        if content_type in self._ALREADY_COMPRESSED:
            return False
        if content_type in self._COMPRESSIBLE:
            return True
        return content_type.startswith("text/") or content_type.startswith("application/")


# ══════════════════════════════════════════════════════════════════════════════
#  4. HIDE SERVER HEADER MIDDLEWARE
# ══════════════════════════════════════════════════════════════════════════════

class HideServerHeaderMiddleware:
    """
    Masks server signature to prevent fingerprinting.
    """

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_server(message):
            if message["type"] == "http.response.start":
                headers = [
                    (k, v) for k, v in message.get("headers", [])
                    if k.lower() not in (b"server", b"x-powered-by")
                ]
                headers.append((b"server", b"webserver"))
                headers.append((b"x-powered-by", b"luviio"))
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_with_server)


# ══════════════════════════════════════════════════════════════════════════════
#  5. SECURITY HEADERS MIDDLEWARE
# ══════════════════════════════════════════════════════════════════════════════

class SecurityHeadersMiddleware:
    """
    Adds security headers to all HTTP responses.
    """

    _HEADERS = [
        (b"x-content-type-options", b"nosniff"),
        (b"x-frame-options", b"DENY"),
        (b"strict-transport-security", b"max-age=31536000; includeSubDomains; preload"),
        (b"referrer-policy", b"strict-origin-when-cross-origin"),
        (b"permissions-policy", b"accelerometer=(), camera=(), geolocation=(), "
         b"gyroscope=(), magnetometer=(), microphone=(), payment=(), usb=()"),
        (b"x-xss-protection", b"0"),
    ]

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_security(message):
            if message["type"] == "http.response.start":
                existing_keys = {k.lower() for k, _ in message.get("headers", [])}
                headers = list(message.get("headers", []))

                for key, value in self._HEADERS:
                    if key not in existing_keys:
                        headers.append((key, value))

                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_with_security)


# ══════════════════════════════════════════════════════════════════════════════
#  EXPORT
# ══════════════════════════════════════════════════════════════════════════════

__all__ = [
    "RequestIDMiddleware",
    "MaxBodySizeMiddleware",
    "GZipMiddleware",
    "HideServerHeaderMiddleware",
    "SecurityHeadersMiddleware",
]
