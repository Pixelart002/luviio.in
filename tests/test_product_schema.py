import pytest
from pydantic import ValidationError

from app.domains.products.schemas import ProductCreate, ProductUpdate


def base_product(**overrides):
    data = {
        "name": "Test Product",
        "price": 100,
        "hsn_code": "731810",
        "gst_percentage": 18,
    }
    data.update(overrides)
    return data


def test_product_create_rejects_invalid_hsn():
    with pytest.raises(ValidationError):
        ProductCreate.model_validate(base_product(hsn_code="Demo"))


def test_product_create_rejects_short_hsn():
    with pytest.raises(ValidationError):
        ProductCreate.model_validate(base_product(hsn_code="731"))


def test_product_update_accepts_slug_and_sku_fields():
    payload = ProductUpdate.model_validate({"slug": "test-product", "sku": "SKU-001"})
    assert payload.slug == "test-product"
    assert payload.sku == "SKU-001"


def test_product_create_accepts_full_catalog_fields():
    payload = ProductCreate.model_validate(
        base_product(
            slug="test-product",
            sku="SKU-001",
            category_id=None,
            short_description="Short",
            description="Long description",
            compare_price=150,
            stock=10,
            low_stock_threshold=2,
            weight_grams=250,
            image_url="https://example.com/product.webp",
            images=["https://example.com/product.webp"],
            attributes={"Material": "Steel"},
            country_of_origin="India",
            seo_title="Test Product",
            seo_description="Test product description",
            seo_keywords="hardware",
            canonical_url="https://luviio.in/products/test-product",
            is_active=True,
        )
    )
    assert payload.hsn_code == "731810"
    assert payload.gst_percentage == 18
