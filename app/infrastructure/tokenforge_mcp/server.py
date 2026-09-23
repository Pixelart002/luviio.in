"""TokenForge MCP server exposed by the Luviio backend.

The server keeps the TokenForge credential server-side and exposes only the
chat operation over MCP. The credential is never accepted from tool callers.
"""

from __future__ import annotations

import httpx
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from app.core.config import settings

TOKENFORGE_BASE_URL = "https://tokenforge.ai.studio"
TOKENFORGE_MESSAGES_URL = f"{TOKENFORGE_BASE_URL}/v1/messages"

mcp = FastMCP(
    "TokenForge Chat",
    stateless_http=True,
    json_response=True,
)


@mcp.tool()
async def tokenforge_chat(
    prompt: str,
    model: str = "glm-5.3",
    max_tokens: int = 1024,
) -> str:
    """Send a chat prompt to TokenForge using the server-side API credential."""
    api_key = settings.TOKENFORGE_API_KEY
    if not api_key:
        return (
            "TokenForge is not configured on the backend. "
            "Set TOKENFORGE_API_KEY in the backend environment first."
        )

    if not prompt.strip():
        return "Prompt must not be empty."

    if not 1 <= max_tokens <= 32768:
        return "max_tokens must be between 1 and 32768."

    payload = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
    }
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }

    try:
        async with httpx.AsyncClient(
            base_url=TOKENFORGE_BASE_URL,
            timeout=httpx.Timeout(60.0, connect=10.0),
        ) as client:
            response = await client.post(
                "/v1/messages",
                headers=headers,
                json=payload,
            )
    except httpx.HTTPError as exc:
        return f"TokenForge request failed: {type(exc).__name__}."

    if response.status_code >= 400:
        return f"TokenForge returned HTTP {response.status_code}."

    try:
        data = response.json()
    except ValueError:
        return "TokenForge returned an invalid JSON response."

    content = data.get("content")
    if isinstance(content, list):
        text_parts = [
            item.get("text", "")
            for item in content
            if isinstance(item, dict) and item.get("type") == "text"
        ]
        text = "".join(part for part in text_parts if isinstance(part, str))
        if text:
            return text

    return "TokenForge returned no text content."


transport_security = TransportSecuritySettings(
    allowed_hosts=[
        "apparent-jordanna-pixelart002-42e39ac6.koyeb.app",
        "apparent-jordanna-pixelart002-42e39ac6.koyeb.app:*",
    ],
    allowed_origins=[
        "https://chatgpt.com",
        "https://chat.openai.com",
    ],
)

mcp_app = mcp.streamable_http_app(
    transport_security=transport_security,
)
