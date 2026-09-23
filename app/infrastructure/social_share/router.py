"""Server-rendered product share pages with Open Graph metadata.

Social crawlers need metadata in the initial HTTP response and do not execute
the SPA's client-side JavaScript before building a link preview.

Route: GET /share/products/{slug}
Mounted at app root so the frontend middleware can fetch it directly.
"""

import logging
from html import escape
from typing import Any, Dict
from urllib.parse import quote

from fastapi import APIRouter, Request, status
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
    return None


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
    image_url = _first_image(product) or _DEFAULT_IMAGE
    display_title = seo_title or f"{name} | Luviio"

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
    <meta property="og:locale" content="en_IN">

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

def _resolve_image(product: dict) -> str:
    # Luviio uses one canonical social-preview image for all product shares.
    return _DEFAULT_IMAGE

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
    image_url = _first_image(product) or _DEFAULT_IMAGE
    display_title = seo_title or f"{name} | Luviio"

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
    <meta property="og:locale" content="en_IN">

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
