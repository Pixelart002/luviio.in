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


def test_product_create_rejects_legacy_non_product_fields():
    with pytest.raises(ValidationError):
        ProductCreate.model_validate(base_product(seo_title="legacy SEO"))


def test_product_update_accepts_hardware_identity_fields():
    payload = ProductUpdate.model_validate(
        {
            "brand": "Luviio",
            "manufacturer": "Luviio",
            "model_number": "HD-001",
            "gtin": "8901234567890",
            "material": "Stainless Steel",
            "finish": "Polished",
            "specifications": {"outlet_size": "110 mm"},
        }
    )
    assert payload.brand == "Luviio"
    assert payload.model_number == "HD-001"
    assert payload.specifications["outlet_size"] == "110 mm"


def test_product_create_accepts_hardware_catalog_fields():
    payload = ProductCreate.model_validate(
        base_product(
            slug="test-product",
            sku="SKU-001",
            category_id=None,
            short_description="Short",
            description="Long description",
            brand="Luviio",
            manufacturer="Luviio",
            model_number="HD-001",
            gtin="8901234567890",
            ean="8901234567890",
            part_number="PART-001",
            key_features=["304 grade", "Floor mount"],
            material="Stainless Steel",
            finish="Polished",
            color="Silver",
            size="150 x 150 mm",
            dimensions="150 x 150 x 50 mm",
            specifications={"outlet_size": "110 mm", "installation_type": "Floor"},
            warranty="1 year",
            compare_price=150,
            stock=10,
            weight_grams=250,
            image_url="https://example.com/product.webp",
            images=["https://example.com/product.webp"],
            country_of_origin="India",
            is_active=True,
        )
    )
    assert payload.hsn_code == "731810"
    assert payload.gst_percentage == 18
    assert payload.specifications["outlet_size"] == "110 mm"
    assert payload.material == "Stainless Steel"
