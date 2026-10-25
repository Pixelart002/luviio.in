"""Server-rendered product share pages with Open Graph metadata.

Social crawlers need metadata in the initial HTTP response and do not execute
the SPA's client-side JavaScript before building a link preview.

Route: GET /share/products/{slug}
Mounted at app root so the frontend middleware can fetch it directly.
"""

import json
import logging
import re
from html import escape
from typing import Any, Dict
from urllib.parse import quote, urlparse, urlunsplit

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


def _canonical_product_url(value: Any, slug: str) -> str:
    """Use only clean product URLs on the configured canonical frontend host."""
    fallback = _frontend_product_url(slug)
    if not isinstance(value, str) or not value.strip():
        return fallback

    try:
        candidate = urlparse(value.strip())
        preferred = urlparse(settings.FRONTEND_URL.rstrip("/"))
        if (
            candidate.scheme != "https"
            or not candidate.hostname
            or candidate.hostname.lower() != (preferred.hostname or "").lower()
            or not re.fullmatch(r"/product/[^/]+/?", candidate.path or "")
        ):
            return fallback
        return urlunsplit(("https", preferred.netloc, (candidate.path or "").rstrip("/"), "", ""))
    except (TypeError, ValueError):
        return fallback


def _image_candidates(product: Dict[str, Any], allowed_host: str | None) -> list[str]:
    """Return ordered, unique HTTPS product images from the trusted storage host.

    Legacy image_url may be stale after gallery changes. Keep it first for
    compatibility, but also inspect the normalized gallery and raw relation so
    the image proxy can fall through to a healthy image rather than the site icon.
    """
    if not allowed_host:
        return []

    candidates: list[str] = []
    seen: set[str] = set()
    sources = (
        product.get("image_url"),
        product.get("images"),
        product.get("product_images"),
    )

    for source in sources:
        if isinstance(source, (str, dict)):
            items = [source]
        elif isinstance(source, list):
            items = source
        else:
            continue

        for item in items:
            if isinstance(item, str):
                candidate = item.strip()
            elif isinstance(item, dict):
                candidate = ""
                for key in ("url", "image_url", "src"):
                    value = item.get(key)
                    if isinstance(value, str) and value.strip():
                        candidate = value.strip()
                        break
            else:
                continue

            if not candidate or candidate in seen:
                continue
            seen.add(candidate)

            try:
                parsed = urlparse(candidate)
                port = parsed.port
            except ValueError:
                continue

            # Keep the image proxy SSRF-safe: only fetch HTTPS objects from
            # the configured Supabase storage host, with no custom port/userinfo.
            if (
                parsed.scheme.lower() != "https"
                or not parsed.hostname
                or parsed.hostname.lower() != allowed_host.lower()
                or port not in (None, 443)
                or parsed.username
                or parsed.password
            ):
                continue

            candidates.append(candidate)

    return candidates


@router.get("/share/products/{slug}/image", include_in_schema=False)
async def product_share_image(slug: str) -> Response:
    """Serve a product's actual storage image, falling through stale image URLs."""
    try:
        product = await ProductService().get_product_for_share(slug)
        configured_host = urlparse(settings.SB_URL).hostname or ""
        candidates = _image_candidates(product, configured_host)

        if not candidates:
            logger.warning("social_share.image_missing_or_untrusted slug=%s", slug)
            return Response(
                status_code=status.HTTP_302_FOUND,
                headers={"Location": _DEFAULT_IMAGE, "Cache-Control": "public, max-age=300"},
            )

        allowed_types = {"image/jpeg", "image/png", "image/webp", "image/gif"}
        max_bytes = 5 * 1024 * 1024

        # A stale image_url must not hide a valid image in the product gallery.
        # Cap attempts and per-request timeout so social preview fetches stay bounded.
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(2.5, connect=1.0),
            follow_redirects=False,
        ) as client:
            for source_image in candidates[:4]:
                try:
                    upstream = await client.get(
                        source_image,
                        headers={"Accept": "image/avif,image/webp,image/png,image/jpeg,image/gif;q=0.9"},
                    )
                except (httpx.HTTPError, ValueError) as exc:
                    logger.warning(
                        "social_share.image_fetch_error slug=%s error=%s",
                        slug,
                        type(exc).__name__,
                    )
                    continue

                if upstream.status_code != 200:
                    logger.warning(
                        "social_share.image_fetch_failed slug=%s status=%s",
                        slug,
                        upstream.status_code,
                    )
                    continue

                media_type = (upstream.headers.get("content-type") or "").split(";", 1)[0].strip().lower()
                if media_type not in allowed_types:
                    logger.warning(
                        "social_share.image_type_rejected slug=%s content_type=%s",
                        slug,
                        media_type,
                    )
                    continue

                content_length = upstream.headers.get("content-length")
                if content_length:
                    try:
                        declared_length = int(content_length)
                    except (TypeError, ValueError):
                        logger.warning("social_share.image_invalid_content_length slug=%s", slug)
                        continue
                    if declared_length < 0 or declared_length > max_bytes:
                        logger.warning("social_share.image_too_large slug=%s", slug)
                        continue

                body = upstream.content
                if len(body) > max_bytes:
                    logger.warning(
                        "social_share.image_too_large_after_fetch slug=%s bytes=%s",
                        slug,
                        len(body),
                    )
                    continue

                return Response(
                    content=body,
                    media_type=media_type,
                    headers={
                        "Cache-Control": "public, max-age=300, s-maxage=3600, stale-while-revalidate=86400",
                        "X-Content-Type-Options": "nosniff",
                    },
                )

        logger.warning("social_share.image_all_candidates_failed slug=%s attempted=%s", slug, min(len(candidates), 4))
        return Response(
            status_code=status.HTTP_302_FOUND,
            headers={"Location": _DEFAULT_IMAGE, "Cache-Control": "public, max-age=300"},
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
        product = await ProductService().get_product_for_share(slug)
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
    if not isinstance(seo, dict):
        seo = {}

    # ProductService projects normalized product_seo values onto flat fields.
    # Read those first; the nested relation is retained as a compatibility fallback.
    seo_title = str(product.get("seo_title") or seo.get("title") or "").strip()
    seo_description = str(product.get("seo_description") or seo.get("description") or "").strip()
    description = (
        seo_description
        or str(product.get("short_description") or "").strip()
        or str(product.get("description") or "").strip()
        or f"Shop {name} on Luviio."
    )

    canonical_url = _canonical_product_url(
        product.get("canonical_url") or seo.get("canonical_url"),
        slug,
    )
    robots_index = product.get("robots_index")
    if robots_index is None:
        robots_index = seo.get("robots_index", True)
    robots_follow = product.get("robots_follow")
    if robots_follow is None:
        robots_follow = seo.get("robots_follow", True)
    index_directive = "index" if robots_index is not False else "noindex"
    follow_directive = "follow" if robots_follow is not False else "nofollow"
    robots_directive = f"{index_directive}, {follow_directive}"
    display_title = seo_title or f"{name} | Luviio"

    # Build product-specific metadata from the product record only. Keep the
    # marketing homepage metadata untouched; this endpoint is for product URLs.
    frontend_origin = settings.FRONTEND_URL.rstrip("/")
    encoded_slug = quote(slug, safe="")
    image_url = f"{frontend_origin}/share/products/{encoded_slug}/image"
    display_title = seo_title or f"{name} | Luviio"
    description = " ".join(description.split())[:300]

    product_jsonld = {
        "@context": "https://schema.org",
        "@type": "Product",
        "name": name,
        "description": description,
        "url": canonical_url,
        "image": [image_url],
    }
    sku = product.get("sku")
    if isinstance(sku, str) and sku.strip():
        product_jsonld["sku"] = sku.strip()

    brand = product.get("brand") or product.get("manufacturer")
    if isinstance(brand, str) and brand.strip():
        product_jsonld["brand"] = {"@type": "Brand", "name": brand.strip()}

    gtin = product.get("gtin") or product.get("ean")
    if isinstance(gtin, str) and gtin.strip():
        product_jsonld["gtin"] = gtin.strip()

    category = product.get("category_name") or product.get("category")
    if isinstance(category, str) and category.strip():
        product_jsonld["category"] = category.strip()

    price = product.get("price")
    # The Luviio storefront is priced in Indian rupees; the products table
    # stores numeric rupee amounts without a per-row currency column.
    currency = str(product.get("currency") or product.get("price_currency") or "INR").strip().upper()
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

        # Never publish invented shipping, return, rating, or review values.
        # Add seller only when a real brand is available from the product record.
        if isinstance(brand, str) and brand.strip():
            offer["seller"] = {"@type": "Organization", "name": "Luviio"}
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
    <meta property="og:image:alt" content="{escaped_name}">
    <meta property="og:locale" content="en_IN">
    <meta name="twitter:card" content="summary_large_image">
    <meta name="twitter:title" content="{escaped_title}">
    <meta name="twitter:description" content="{escaped_description}">
    <meta name="twitter:image" content="{escaped_image}">
    <meta name="twitter:image:alt" content="{escaped_name}">
    <meta name="robots" content="{escape(robots_directive, quote=True)}, max-image-preview:large">

    <script type="application/ld+json">{jsonld}</script>

</head>
<body>
    <main>
        <img src="{escaped_image}" alt="{escaped_name}" style="max-width:100%;height:auto">
        <p>View <a href="{escaped_url}">{escaped_title}</a> on Luviio.</p>
    </main>
</body>
</html>"""

    return HTMLResponse(
        content=html,
        status_code=status.HTTP_200_OK,
        headers={
            "Cache-Control": "public, max-age=60, s-maxage=300, stale-while-revalidate=86400",
            "X-Robots-Tag": robots_directive,
        },
    )
