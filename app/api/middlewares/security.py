"""
Security Middleware — Production Grade
======================================
Path: app/api/middlewares/security.py

ASGI middleware for request tracing, body-size protection, compression,
server-header hardening, and security response headers.
"""
import gzip
import io
import uuid
import logging

logger = logging.getLogger(__name__)


class RequestIDMiddleware:
    """Generate a server-owned request ID and expose it to the application/client."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = str(uuid.uuid4())
        headers = [
            (k, v) for k, v in scope.get("headers", [])
            if k.lower() != b"x-request-id"
        ]
        headers.append((b"x-request-id", request_id.encode()))
        scope = {**scope, "headers": headers}

        async def send_with_id(message):
            if message["type"] == "http.response.start":
                response_headers = [
                    (k, v) for k, v in message.get("headers", [])
                    if k.lower() != b"x-request-id"
                ]
                response_headers.append((b"x-request-id", request_id.encode()))
                message = {**message, "headers": response_headers}
            await send(message)

        await self.app(scope, receive, send_with_id)


class MaxBodySizeMiddleware:
    """Reject request bodies larger than the configured limit, including chunked bodies."""

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
                if int(content_length_raw) > self.max_bytes:
                    await self._send_413(send, scope.get("path", "?"), int(content_length_raw))
                    return
            except ValueError:
                pass

        total_bytes = 0

        async def receive_wrapper():
            nonlocal total_bytes
            message = await receive()
            if message["type"] == "http.request":
                total_bytes += len(message.get("body", b""))
                if total_bytes > self.max_bytes:
                    raise RuntimeError("Request body exceeded maximum size limit")
            return message

        try:
            await self.app(scope, receive_wrapper, send)
        except RuntimeError as exc:
            if "maximum size limit" in str(exc):
                await self._send_413(send, scope.get("path", "?"), total_bytes)
            else:
                raise

    async def _send_413(self, send, path: str, size: int):
        logger.warning("Body too large | size=%d max=%d path=%s", size, self.max_bytes, path)
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


class GZipMiddleware:
    """Compress complete text responses without buffering streaming responses."""

    _COMPRESSIBLE = {
        "application/json", "application/javascript", "application/xml",
        "text/html", "text/css", "text/plain", "text/javascript", "text/xml",
    }
    _ALREADY_COMPRESSED = {
        "image/png", "image/jpeg", "image/webp", "image/gif", "image/svg+xml",
        "video/mp4", "video/webm", "audio/mpeg", "audio/ogg", "application/zip",
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

        accept_encoding = dict(scope.get("headers", [])).get(b"accept-encoding", b"").decode("latin-1", errors="ignore").lower()
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
                for key, value in response_headers:
                    if key.lower() == b"content-type":
                        content_type = value.decode("latin-1", errors="ignore").split(";")[0].strip().lower()
            elif message["type"] == "http.response.body":
                if not started:
                    if message.get("more_body", False):
                        await send({"type": "http.response.start", "status": response_status, "headers": response_headers})
                        await send(message)
                    else:
                        await self._send_compressed(send, response_status, response_headers, message.get("body", b""), content_type)
                    started = True
                else:
                    await send(message)

        await self.app(scope, receive, intercept_send)

    async def _send_compressed(self, send, status, headers, body, content_type):
        if not self._should_compress(body, content_type):
            await send({"type": "http.response.start", "status": status, "headers": headers})
            await send({"type": "http.response.body", "body": body})
            return

        try:
            buf = io.BytesIO()
            with gzip.GzipFile(fileobj=buf, mode="wb", compresslevel=self.compression_level) as gz:
                gz.write(body)
            compressed = buf.getvalue()
            final_headers = [
                (k, v) for k, v in headers
                if k.lower() not in (b"content-length", b"content-encoding")
            ]
            final_headers.extend([
                (b"content-encoding", b"gzip"),
                (b"content-length", str(len(compressed)).encode()),
                (b"vary", b"Accept-Encoding"),
            ])
            await send({"type": "http.response.start", "status": status, "headers": final_headers})
            await send({"type": "http.response.body", "body": compressed})
        except Exception:
            logger.exception("GZip failed; sending uncompressed response")
            await send({"type": "http.response.start", "status": status, "headers": headers})
            await send({"type": "http.response.body", "body": body})

    def _should_compress(self, body: bytes, content_type: str) -> bool:
        if len(body) < self.min_size or content_type in self._ALREADY_COMPRESSED:
            return False
        return content_type in self._COMPRESSIBLE or content_type.startswith("text/") or content_type.startswith("application/")


class HideServerHeaderMiddleware:
    """Remove framework/server fingerprint headers instead of replacing them with another fingerprint."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_hardened(message):
            if message["type"] == "http.response.start":
                headers = [
                    (k, v) for k, v in message.get("headers", [])
                    if k.lower() not in (b"server", b"x-powered-by")
                ]
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_hardened)


class SecurityHeadersMiddleware:
    """Add baseline browser security headers; HSTS is emitted only over HTTPS."""

    _HEADERS = [
        (b"x-content-type-options", b"nosniff"),
        (b"x-frame-options", b"DENY"),
        (b"referrer-policy", b"strict-origin-when-cross-origin"),
        (b"permissions-policy", b"accelerometer=(), camera=(), geolocation=(), gyroscope=(), magnetometer=(), microphone=(), payment=(), usb=()"),
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
                existing = {k.lower() for k, _ in message.get("headers", [])}
                headers = list(message.get("headers", []))
                for key, value in self._HEADERS:
                    if key not in existing:
                        headers.append((key, value))
                if scope.get("scheme") == "https" and b"strict-transport-security" not in existing:
                    headers.append((b"strict-transport-security", b"max-age=31536000; includeSubDomains; preload"))
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_with_security)


__all__ = [
    "RequestIDMiddleware", "MaxBodySizeMiddleware", "GZipMiddleware",
    "HideServerHeaderMiddleware", "SecurityHeadersMiddleware",
]
