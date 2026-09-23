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
        ProductCreate.model_validate(base_product(legacy_field="legacy value"))


def test_product_create_rejects_generic_json_specifications():
    with pytest.raises(ValidationError):
        ProductCreate.model_validate(base_product(specifications={"outlet_size": "110 mm"}))


def test_product_update_accepts_hardware_identity_fields():
    payload = ProductUpdate.model_validate(
        {
            "brand": "Luviio",
            "manufacturer": "Luviio",
            "model_number": "HD-001",
            "gtin": "8901234567890",
            "material": "Stainless Steel",
            "finish": "Polished",
        }
    )
    assert payload.brand == "Luviio"
    assert payload.model_number == "HD-001"


def test_product_update_rejects_generic_json_specifications():
    with pytest.raises(ValidationError):
        ProductUpdate.model_validate({"specifications": {"outlet_size": "110 mm"}})


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
            warranty="1 year",
            compare_price=150,
            stock=10,
            weight=250, weight_unit="g",
            image_url="https://example.com/product.webp",
            images=["https://example.com/product.webp"],
            country_of_origin="India",
            is_active=True,
        )
    )
    assert payload.hsn_code == "731810"
    assert payload.gst_percentage == 18
    assert payload.material == "Stainless Steel"



def test_product_weight_accepts_kg_scale():
    product = ProductCreate(
        name="Weighted hardware",
        price=100,
        weight=1.25,
        weight_unit="kg",
        hsn_code="73249000",
        gst_percentage=18,
    )
    assert product.weight == 1.25
    assert product.weight_unit == "kg"


def test_product_create_accepts_single_generic_measurement():
    payload = ProductCreate(
        name="Measured hardware",
        price=100,
        measurement_type="weight",
        measurement_value=1.25,
        measurement_unit="kg",
        hsn_code="73249000",
        gst_percentage=18,
    )
    assert payload.measurement_type == "weight"
    assert payload.measurement_value == 1.25
    assert payload.measurement_unit == "kg"


def test_product_weight_rejects_invalid_unit():
    with pytest.raises(ValidationError):
        ProductCreate(
            name="Weighted hardware",
            price=100,
            weight=250,
            weight_unit="lb",
            hsn_code="73249000",
            gst_percentage=18,
        )



def test_product_measurement_scales_accept_volume_dimensions_and_quantity():
    product = ProductCreate(
        name="Measurement hardware",
        price=100,
        volume=1.5,
        volume_unit="L",
        dimensions="150 x 100 x 50 mm",
        quantity=2,
        quantity_unit="piece",
        hsn_code="73249000",
        gst_percentage=18,
    )
    assert product.volume == 1.5
    assert product.volume_unit == "L"
    assert product.dimensions == "150 x 100 x 50 mm"
    assert product.quantity_unit == "piece"


def test_product_rejects_legacy_dimension_fields():
    with pytest.raises(ValidationError):
        ProductCreate(
            name="Legacy dimensions",
            price=100,
            length=150,
            hsn_code="73249000",
            gst_percentage=18,
        )


def test_product_measurement_requires_units():
    with pytest.raises(ValidationError):
        ProductCreate(
            name="Missing volume unit",
            price=100,
            volume=1,
            hsn_code="73249000",
            gst_percentage=18,
        )
    with pytest.raises(ValidationError):
        ProductCreate(
            name="Missing dimension unit",
            price=100,
            length=100,
            hsn_code="73249000",
            gst_percentage=18,
        )
    with pytest.raises(ValidationError):
        ProductCreate(
            name="Missing quantity unit",
            price=100,
            quantity=2,
            hsn_code="73249000",
            gst_percentage=18,
        )
