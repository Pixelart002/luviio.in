"""Server-rendered product share pages with Open Graph metadata.

Social crawlers need metadata in the initial HTTP response and do not execute
the SPA's client-side JavaScript before building a link preview.

Route: GET /share/products/{slug}
Mounted at app root so the frontend middleware can fetch it directly.
"""

import json
import logging
from html import escape
from typing import Any, Dict
from urllib.parse import quote, urlparse

import httpx
from fastapi import APIRouter, Request, Response, status
from fastapi.exceptions import HTTPException
from fastapi.responses import HTMLResponse

from app.core.config import settings
from app.domains.products.service import ProductService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Social Share"])

_DEFAULT_IMAGE = f"{settings.FRONTEND_URL.rstrip('/')}/icon-512.png"


def _frontend_product_url(slug: str) -> str:
    base = settings.FRONTEND_URL.rstrip("/")
    return f"{base}/product/{quote(slug, safe='')}"


def _first_image(product: Dict[str, Any]) -> str | None:
    image_url = product.get("image_url")
    if image_url and isinstance(image_url, str) and image_url.startswith("http"):
        return image_url
    images = product.get("images") or []
    for img in images:
        if isinstance(img, str) and img.startswith("http"):
            return img
        if isinstance(img, dict):
            candidate = img.get("url") or img.get("image_url") or img.get("src")
            if isinstance(candidate, str) and candidate.startswith("http"):
                return candidate
    return None


@router.get("/share/products/{slug}/image", include_in_schema=False)
async def product_share_image(slug: str) -> Response:
    """Proxy a product image from the trusted public Supabase storage host."""
    try:
        product = await ProductService().get_product(slug)
        source_image = _first_image(product)
        if not source_image:
            return Response(
                status_code=status.HTTP_302_FOUND,
                headers={"Location": _DEFAULT_IMAGE, "Cache-Control": "public, max-age=300"},
            )

        parsed = urlparse(source_image)
        configured_host = urlparse(settings.SB_URL).hostname
        if parsed.scheme != "https" or not parsed.hostname or parsed.hostname != configured_host:
            logger.warning("social_share.image_rejected slug=%s host=%s", slug, parsed.hostname)
            return Response(
                status_code=status.HTTP_302_FOUND,
                headers={"Location": _DEFAULT_IMAGE, "Cache-Control": "public, max-age=300"},
            )

        async with httpx.AsyncClient(
            timeout=httpx.Timeout(5.0, connect=2.0),
            follow_redirects=False,
        ) as client:
            upstream = await client.get(
                source_image,
                headers={"Accept": "image/avif,image/webp,image/png,image/jpeg,image/gif;q=0.9"},
            )

        if upstream.status_code != 200:
            logger.warning("social_share.image_fetch_failed slug=%s status=%s", slug, upstream.status_code)
            return Response(
                status_code=status.HTTP_302_FOUND,
                headers={"Location": _DEFAULT_IMAGE, "Cache-Control": "public, max-age=300"},
            )

        media_type = (upstream.headers.get("content-type") or "").split(";", 1)[0].strip().lower()
        allowed_types = {"image/jpeg", "image/png", "image/webp", "image/gif"}
        if media_type not in allowed_types:
            logger.warning("social_share.image_type_rejected slug=%s content_type=%s", slug, media_type)
            return Response(
                status_code=status.HTTP_302_FOUND,
                headers={"Location": _DEFAULT_IMAGE, "Cache-Control": "public, max-age=300"},
            )

        content_length = upstream.headers.get("content-length")
        if content_length:
            try:
                if int(content_length) > 5 * 1024 * 1024:
                    raise ValueError("image too large")
            except ValueError:
                logger.warning("social_share.image_too_large slug=%s", slug)
                return Response(
                    status_code=status.HTTP_302_FOUND,
                    headers={"Location": _DEFAULT_IMAGE, "Cache-Control": "public, max-age=300"},
                )

        body = upstream.content
        if len(body) > 5 * 1024 * 1024:
            logger.warning("social_share.image_too_large_after_fetch slug=%s bytes=%s", slug, len(body))
            return Response(
                status_code=status.HTTP_302_FOUND,
                headers={"Location": _DEFAULT_IMAGE, "Cache-Control": "public, max-age=300"},
            )

        return Response(
            content=body,
            media_type=media_type,
            headers={
                "Cache-Control": "public, max-age=300, s-maxage=3600, stale-while-revalidate=86400",
                "X-Content-Type-Options": "nosniff",
            },
        )
    except Exception:
        logger.exception("social_share.image_proxy_error slug=%s", slug)
        return Response(
            status_code=status.HTTP_302_FOUND,
            headers={"Location": _DEFAULT_IMAGE, "Cache-Control": "public, max-age=300"},
        )


@router.get("/share/products/{slug}", response_class=HTMLResponse, include_in_schema=False)
async def product_share_page(request: Request, slug: str) -> HTMLResponse:
    """Return crawler-readable OG metadata for a product."""
    try:
        product = await ProductService().get_product(slug)
    except HTTPException as exc:
        if exc.status_code == status.HTTP_404_NOT_FOUND:
            return HTMLResponse(
                content="<html><head><title>Not found</title></head><body>Product not found.</body></html>",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        logger.error("social_share.product_fetch_error slug=%s status=%s", slug, exc.status_code)
        return HTMLResponse(
            content="<html><head><title>Error</title></head><body>Temporarily unavailable.</body></html>",
            status_code=status.HTTP_502_BAD_GATEWAY,
        )
    except Exception:
        logger.exception("social_share.unexpected_error slug=%s", slug)
        return HTMLResponse(
            content="<html><head><title>Error</title></head><body>Temporarily unavailable.</body></html>",
            status_code=status.HTTP_502_BAD_GATEWAY,
        )

    name = str(product.get("name") or "Luviio Product").strip()
    seo = product.get("product_seo") or {}
    seo_title = str(seo.get("title") or "").strip() if isinstance(seo, dict) else ""
    seo_description = str(seo.get("description") or "").strip() if isinstance(seo, dict) else ""

    description = (
        seo_description
        or str(product.get("short_description") or "").strip()
        or str(product.get("description") or "").strip()
        or f"Shop {name} on Luviio."
    )

    canonical_url = _frontend_product_url(slug)
    image_url = f"{settings.FRONTEND_URL.rstrip('/')}/share/products/{quote(slug, safe='')}/image"
    display_title = seo_title or f"{name} | Luviio"

    product_jsonld = {
        "@context": "https://schema.org",
        "@type": "Product",
        "name": name,
        "description": description[:500],
        "url": canonical_url,
        "image": [image_url],
    }
    brand = product.get("brand")
    if brand:
        product_jsonld["brand"] = {"@type": "Brand", "name": str(brand).strip()}

    price = product.get("price")
    currency = str(product.get("currency") or product.get("price_currency") or "").strip().upper()
    try:
        numeric_price = float(price) if price is not None else None
    except (TypeError, ValueError):
        numeric_price = None

    if numeric_price is not None and numeric_price >= 0 and currency:
        offer = {
            "@type": "Offer",
            "url": canonical_url,
            "price": numeric_price,
            "priceCurrency": currency,
        }
        stock = product.get("stock")
        try:
            if stock is not None:
                offer["availability"] = (
                    "https://schema.org/InStock"
                    if float(stock) > 0
                    else "https://schema.org/OutOfStock"
                )
        except (TypeError, ValueError):
            pass
        product_jsonld["offers"] = offer

    jsonld = json.dumps(product_jsonld, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")

    escaped_title = escape(display_title, quote=True)
    escaped_name = escape(name, quote=True)
    escaped_description = escape(description[:300], quote=True)
    escaped_url = escape(canonical_url, quote=True)
    escaped_image = escape(image_url, quote=True)

    html = f"""<!doctype html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{escaped_title}</title>
    <meta name="description" content="{escaped_description}">
    <link rel="canonical" href="{escaped_url}">

    <meta property="og:type" content="product">
    <meta property="og:site_name" content="Luviio">
    <meta property="og:title" content="{escaped_title}">
    <meta property="og:description" content="{escaped_description}">
    <meta property="og:url" content="{escaped_url}">
    <meta property="og:image" content="{escaped_image}">
    <meta property="og:image:secure_url" content="{escaped_image}">
    <meta property="og:image:width" content="1200">
    <meta property="og:image:height" content="630">
    <meta property="og:image:alt" content="{escaped_name}">
    <meta property="og:image:type" content="image/jpeg">
    <meta property="og:locale" content="en_IN">
    <meta name="robots" content="index, follow, max-image-preview:large">

    <script type="application/ld+json">{jsonld}</script>

    <meta name="twitter:card" content="summary_large_image">
    <meta name="twitter:title" content="{escaped_title}">
    <meta name="twitter:description" content="{escaped_description}">
    <meta name="twitter:image" content="{escaped_image}">
    <meta name="twitter:image:alt" content="{escaped_name}">

    <meta http-equiv="refresh" content="0;url={escaped_url}">
</head>
<body>
    <p>Opening <a href="{escaped_url}">{escaped_title}</a>…</p>
</body>
</html>"""

    return HTMLResponse(
        content=html,
        status_code=status.HTTP_200_OK,
        headers={
            "Cache-Control": "public, max-age=60, s-maxage=300, stale-while-revalidate=86400",
            "X-Robots-Tag": "index, follow",
        },
    )
