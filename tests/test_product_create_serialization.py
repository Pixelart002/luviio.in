from uuid import uuid4

import pytest

from app.domains.products.schemas import ProductCreate
from app.domains.products.service import ProductService


class FakeProductRepository:
    async def check_sku_exists(self, sku, exclude_product_id=None):
        return False

    async def generate_unique_slug(self, base_slug, exclude_product_id=None):
        return base_slug

    async def get_measurement_definition(self, measurement_type, measurement_unit):
        if measurement_type == "weight" and measurement_unit == "kg":
            return {
                "measurement_type": "weight",
                "code": "kg",
                "multiplier": 1000,
            }
        return None


@pytest.mark.asyncio
async def test_product_create_payload_is_json_safe_and_normalizes_numeric_fields():
    category_id = uuid4()
    payload = ProductCreate.model_validate(
        {
            "name": "Measured hardware",
            "category_id": str(category_id),
            "price": "125.50",
            "weight": "1.25",
            "weight_unit": "kg",
            "measurement_type": "weight",
            "measurement_value": "1.25",
            "measurement_unit": "kg",
            "hsn_code": "73249000",
            "gst_percentage": 18,
        }
    )

    # The plain model_dump() leaves UUID/Decimal objects that json.dumps cannot encode.
    data = payload.model_dump(mode="json")
    assert data["category_id"] == str(category_id)

    service = ProductService()
    service.repo = FakeProductRepository()
    prepared = await service._prepare_product_data(data)

    assert prepared["category_id"] == str(category_id)
    assert prepared["price"] == 125.5
    assert prepared["weight"] == 1250.0
    assert prepared["measurement_value"] == 1.25
    assert isinstance(prepared["price"], float)
    assert isinstance(prepared["measurement_value"], float)
