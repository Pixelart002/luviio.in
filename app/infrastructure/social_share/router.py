"""Server-rendered product share pages with Open Graph metadata."""

from html import escape
from typing import Any, Dict
from urllib.parse import quote

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app.core.config import settings
from app.domains.products.service import ProductService

router = APIRouter(tags=["Social Share"])


def _frontend_product_url(slug: str) -> str:
    base = settings.FRONTEND_URL.rstrip("/")
    return f"{base}/products/{quote(slug, safe='')}"


def _first_image(product: Dict[str, Any]) -> str | None:
    images = product.get("images") or []
    if images and isinstance(images[0], str):
        return images[0]
    image_url = product.get("image_url")
    return image_url if isinstance(image_url, str) else None


@router.get("/share/products/{slug}", response_class=HTMLResponse, include_in_schema=False)
async def product_share_page(request: Request, slug: str) -> HTMLResponse:
    """Return crawler-readable OG metadata and redirect visitors to the SPA."""
    product = await ProductService().get_product(slug)

    name = str(product.get("name") or "Luviio Product")
    description = str(
        product.get("short_description")
        or product.get("description")
        or "Shop this product on Luviio."
    ).strip()
    canonical_url = _frontend_product_url(slug)
    image_url = _first_image(product)

    title = f"{name} | Luviio"
    escaped_title = escape(title, quote=True)
    escaped_name = escape(name, quote=True)
    escaped_description = escape(description[:300], quote=True)
    escaped_url = escape(canonical_url, quote=True)

    image_tags = ""
    if image_url:
        escaped_image = escape(image_url, quote=True)
        image_tags = f'''\n    <meta property="og:image" content="{escaped_image}">\n    <meta property="og:image:alt" content="{escaped_name}">\n    <meta name="twitter:image" content="{escaped_image}">'''

    html = f"""<!doctype html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{escaped_title}</title>
    <meta name="description" content="{escaped_description}">
    <meta property="og:type" content="product">
    <meta property="og:title" content="{escaped_title}">
    <meta property="og:description" content="{escaped_description}">
    <meta property="og:url" content="{escaped_url}">{image_tags}
    <meta name="twitter:card" content="summary_large_image">
    <meta name="twitter:title" content="{escaped_title}">
    <meta name="twitter:description" content="{escaped_description}">
    <link rel="canonical" href="{escaped_url}">
    <meta http-equiv="refresh" content="0;url={escaped_url}">
</head>
<body>
    <p>Opening <a href="{escaped_url}">{escaped_title}</a>…</p>
    <script>window.location.replace({canonical_url!r});</script>
</body>
</html>"""
    return HTMLResponse(content=html)
