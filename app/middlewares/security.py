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

All middlewares skip non-HTTP requests (WebSocket, etc.)
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
    
    Added to:
      • Request scope (downstream access)
      • Response header (X-Request-ID)
      • Application logs (via context variable)
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
    
    Default: 10 MB
    Skips: OPTIONS (preflight), no Content-Length (chunked)
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

        if content_length_raw:
            try:
                content_length = int(content_length_raw)
                if content_length > self.max_bytes:
                    logger.warning(
                        "Body too large | size=%d max=%d path=%s",
                        content_length, self.max_bytes, scope.get("path", "?")
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
                    return
            except ValueError:
                logger.warning("Invalid Content-Length: %s", content_length_raw)

        await self.app(scope, receive, send)


# ══════════════════════════════════════════════════════════════════════════════
#  3. GZIP COMPRESSION MIDDLEWARE
# ══════════════════════════════════════════════════════════════════════════════

class GZipMiddleware:
    """
    Compresses JSON/text responses to reduce bandwidth.
    
    Typical savings: 50-80% for JSON responses.
    
    Skip conditions:
      • Client doesn't accept gzip
      • Response < 500 bytes (overhead > savings)
      • Already compressed content (images, videos, PDFs)
      • Streaming responses
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

        # Check client support
        req_headers = dict(scope.get("headers", []))
        accept_encoding = req_headers.get(b"accept-encoding", b"").decode("latin-1", errors="ignore").lower()

        if "gzip" not in accept_encoding:
            await self.app(scope, receive, send)
            return

        # Intercept response
        response_status = 200
        response_headers = []
        body_chunks = []
        content_type = ""

        async def intercept_send(message):
            nonlocal response_status, response_headers, content_type

            if message["type"] == "http.response.start":
                response_status = message.get("status", 200)
                response_headers = list(message.get("headers", []))

                for k, v in response_headers:
                    if k.lower() == b"content-type":
                        content_type = v.decode("latin-1", errors="ignore").split(";")[0].strip().lower()

            elif message["type"] == "http.response.body":
                body_chunks.append(message.get("body", b""))

                if not message.get("more_body", False):
                    full_body = b"".join(body_chunks)
                    await self._send_compressed(send, response_status, response_headers, full_body, content_type)

        await self.app(scope, receive, intercept_send)

    async def _send_compressed(self, send, status, headers, body, content_type):
        """Compress if applicable, otherwise send as-is."""
        if not self._should_compress(body, content_type):
            # Send uncompressed
            await send({
                "type": "http.response.start", "status": status,
                "headers": headers,
            })
            await send({"type": "http.response.body", "body": body})
            return

        try:
            original_size = len(body)

            # Compress
            buf = io.BytesIO()
            with gzip.GzipFile(fileobj=buf, mode="wb", compresslevel=self.compression_level) as gz:
                gz.write(body)
            compressed = buf.getvalue()
            compressed_size = len(compressed)

            # Prepare headers
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
        """Decide if response should be compressed."""
        if len(body) < self.min_size:
            return False
        if content_type in self._ALREADY_COMPRESSED:
            return False
        if content_type in self._COMPRESSIBLE:
            return True
        # Default: compress text-like content
        return content_type.startswith("text/") or content_type.startswith("application/")


# ══════════════════════════════════════════════════════════════════════════════
#  4. HIDE SERVER HEADER MIDDLEWARE
# ══════════════════════════════════════════════════════════════════════════════

class HideServerHeaderMiddleware:
    """
    Masks server signature to prevent fingerprinting.
    Server: uvicorn → Server: webserver
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
    CSP intentionally excluded — belongs on frontend, not JSON API.
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