from importlib import import_module
from unittest.mock import AsyncMock


def test_product_share_page_contains_dynamic_og_metadata(client, monkeypatch):
    product = {
        "name": "Premium Drain Cover",
        "slug": "premium-drain-cover",
        "short_description": "Durable drain cover for everyday use.",
        "images": ["https://cdn.example.com/products/drain-cover.webp"],
        "image_url": "https://cdn.example.com/products/drain-cover.webp",
    }

    mock_service = type("MockProductService", (), {"get_product": AsyncMock(return_value=product)})
    router_module = import_module("app.infrastructure.social_share.router")
    monkeypatch.setattr(router_module, "ProductService", mock_service)

    response = client.get("/share/products/premium-drain-cover")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert '<meta property="og:title" content="Premium Drain Cover | Luviio">' in response.text
    assert '<meta property="og:description" content="Durable drain cover for everyday use.">' in response.text
    assert '<meta property="og:image" content="https://www.luviio.in/share/products/premium-drain-cover/image">' in response.text
    assert '<meta property="og:url" content="https://www.luviio.in/product/premium-drain-cover">' in response.text
    assert '<meta name="twitter:card" content="summary_large_image">' in response.text


def test_product_share_page_escapes_metadata(client, monkeypatch):
    product = {
        "name": 'A <script>alert("x")</script> item',
        "slug": "safe-item",
        "short_description": 'Use "safe" & reliable.',
        "images": [],
    }

    mock_service = type("MockProductService", (), {"get_product": AsyncMock(return_value=product)})
    router_module = import_module("app.infrastructure.social_share.router")
    monkeypatch.setattr(router_module, "ProductService", mock_service)

    response = client.get("/share/products/safe-item")

    assert response.status_code == 200
    assert "<script>alert(\"x\")</script>" not in response.text
    assert "&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt;" in response.text
    assert "Use &quot;safe&quot; &amp; reliable." in response.text



def test_product_share_page_uses_flat_seo_fields_and_clean_canonical(client, monkeypatch):
    product = {
        "name": "Square sink waste coupling",
        "slug": "sink-waste-coupling",
        "seo_title": "4.5-Inch Square Sink Coupling | Luviio",
        "seo_description": "A stainless-steel square sink coupling with a removable grid basket.",
        "canonical_url": "https://www.luviio.in/product/sink-waste-coupling?utm_source=legacy#details",
        "robots_index": False,
        "robots_follow": True,
        "sku": "LUV-SAN-SQCPL-45",
        "short_description": "Generic catalogue description.",
        "image_url": "https://cdn.example.com/products/coupling.webp",
        "images": ["https://cdn.example.com/products/coupling.webp"],
        "price": 249,
        "stock": 32,
    }

    mock_service = type("MockProductService", (), {"get_product": AsyncMock(return_value=product)})
    router_module = import_module("app.infrastructure.social_share.router")
    monkeypatch.setattr(router_module, "ProductService", mock_service)

    response = client.get("/share/products/sink-waste-coupling")

    assert response.status_code == 200
    assert '<title>4.5-Inch Square Sink Coupling | Luviio</title>' in response.text
    assert 'content="A stainless-steel square sink coupling with a removable grid basket."' in response.text
    assert '<link rel="canonical" href="https://www.luviio.in/product/sink-waste-coupling">' in response.text
    assert '<meta property="og:url" content="https://www.luviio.in/product/sink-waste-coupling">' in response.text
    assert '<meta name="robots" content="noindex, follow, max-image-preview:large">' in response.text
    assert response.headers["x-robots-tag"] == "noindex, follow"
    assert '"sku":"LUV-SAN-SQCPL-45"' in response.text
    assert '"priceCurrency":"INR"' in response.text
    assert "Generic catalogue description." not in response.text


def test_product_share_page_rejects_off_host_canonical_and_honors_no_follow(client, monkeypatch):
    product = {
        "name": "Safe drain cover",
        "slug": "safe-drain-cover",
        "canonical_url": "https://example.com/product/not-luviio",
        "robots_index": True,
        "robots_follow": False,
        "images": [],
    }

    mock_service = type("MockProductService", (), {"get_product": AsyncMock(return_value=product)})
    router_module = import_module("app.infrastructure.social_share.router")
    monkeypatch.setattr(router_module, "ProductService", mock_service)

    response = client.get("/share/products/safe-drain-cover")

    assert response.status_code == 200
    assert '<link rel="canonical" href="https://www.luviio.in/product/safe-drain-cover">' in response.text
    assert '<meta name="robots" content="index, nofollow, max-image-preview:large">' in response.text
    assert response.headers["x-robots-tag"] == "index, nofollow"

def test_product_share_image_falls_through_stale_primary_to_gallery_image(client, monkeypatch):
    router_module = import_module("app.infrastructure.social_share.router")
    storage_host = "project.supabase.co"
    stale_image = f"https://{storage_host}/storage/v1/object/public/product-images/stale.webp"
    working_image = f"https://{storage_host}/storage/v1/object/public/product-images/working.webp"
    image_bytes = b"verified-product-webp-payload"
    attempted_urls = []

    product = {
        "name": "Square floor drainer",
        "slug": "square-floor-drainer",
        "image_url": stale_image,
        "images": [stale_image, working_image],
    }
    mock_service = type(
        "MockProductService",
        (),
        {"get_product": AsyncMock(return_value=product)},
    )
    monkeypatch.setattr(router_module, "ProductService", mock_service)
    monkeypatch.setattr(router_module.settings, "SB_URL", f"https://{storage_host}")

    class MockUpstreamResponse:
        def __init__(self, status_code, body=b"", content_type="image/webp"):
            self.status_code = status_code
            self.content = body
            self.headers = {
                "content-type": content_type,
                "content-length": str(len(body)),
            }

    class MockAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def get(self, url, headers=None):
            attempted_urls.append(url)
            if url == stale_image:
                return MockUpstreamResponse(404, content_type="text/plain")
            return MockUpstreamResponse(200, image_bytes)

    monkeypatch.setattr(router_module.httpx, "AsyncClient", MockAsyncClient)

    response = client.get("/share/products/square-floor-drainer/image")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/webp")
    assert response.content == image_bytes
    assert attempted_urls == [stale_image, working_image]


def test_image_candidates_reject_insecure_and_untrusted_hosts():
    router_module = import_module("app.infrastructure.social_share.router")
    trusted = "project.supabase.co"
    valid_image = f"https://{trusted}/storage/v1/object/public/product-images/valid.webp"

    candidates = router_module._image_candidates(
        {
            "image_url": "http://project.supabase.co/storage/old.webp",
            "images": [
                "https://untrusted.example/asset.webp",
                {"url": valid_image},
            ],
        },
        trusted,
    )

    assert candidates == [valid_image]

