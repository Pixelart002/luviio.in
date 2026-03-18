import uuid


class HideServerHeaderMiddleware:
    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
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


class SecurityHeadersMiddleware:
    def __init__(self, app) -> None:
        self.app = app

    # FIX: CSP removed from API middleware.
    # `default-src 'none'` is a browser/document policy — wrong on a JSON API.
    # It was also leaking into CORS preflight responses and breaking OPTIONS.
    # CSP belongs on your frontend (Vercel headers config), not the API.
    _HEADERS = [
        (b"x-content-type-options",    b"nosniff"),
        (b"x-frame-options",           b"DENY"),
        (b"strict-transport-security", b"max-age=31536000; includeSubDomains; preload"),
        (b"referrer-policy",           b"strict-origin-when-cross-origin"),
        (b"permissions-policy",        b"geolocation=(), camera=(), microphone=(), payment=()"),
    ]

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_security(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", [])) + self._HEADERS
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_with_security)


class MaxBodySizeMiddleware:
    def __init__(self, app, max_bytes: int = 10 * 1024 * 1024) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # FIX: Skip body check for OPTIONS — preflight has no body
        if scope.get("method") == "OPTIONS":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))
        content_length = headers.get(b"content-length")
        if content_length and int(content_length) > self.max_bytes:
            response = b'{"detail":"Request body too large"}'
            await send({
                "type": "http.response.start",
                "status": 413,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(response)).encode()),
                ],
            })
            await send({"type": "http.response.body", "body": response})
            return

        await self.app(scope, receive, send)


class RequestIDMiddleware:
    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = str(uuid.uuid4())[:8]
        existing_headers = list(scope.get("headers", []))
        existing_headers.append((b"x-request-id", request_id.encode()))
        scope = {**scope, "headers": existing_headers}

        async def send_with_id(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.append((b"x-request-id", request_id.encode()))
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_with_id)