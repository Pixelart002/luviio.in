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
    monkeypatch.setattr("app.infrastructure.social_share.router.ProductService", mock_service)

    response = client.get("/share/products/premium-drain-cover")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert '<meta property="og:title" content="Premium Drain Cover | Luviio">' in response.text
    assert '<meta property="og:description" content="Durable drain cover for everyday use.">' in response.text
    assert '<meta property="og:image" content="https://cdn.example.com/products/drain-cover.webp">' in response.text
    assert '<meta property="og:url" content="https://www.luviio.in/products/premium-drain-cover">' in response.text
    assert '<meta name="twitter:card" content="summary_large_image">' in response.text


def test_product_share_page_escapes_metadata(client, monkeypatch):
    product = {
        "name": 'A <script>alert("x")</script> item',
        "slug": "safe-item",
        "short_description": 'Use "safe" & reliable.',
        "images": [],
    }

    mock_service = type("MockProductService", (), {"get_product": AsyncMock(return_value=product)})
    monkeypatch.setattr("app.infrastructure.social_share.router.ProductService", mock_service)

    response = client.get("/share/products/safe-item")

    assert response.status_code == 200
    assert "<script>alert(\"x\")</script>" not in response.text
    assert "&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt;" in response.text
    assert "Use &quot;safe&quot; &amp; reliable." in response.text
