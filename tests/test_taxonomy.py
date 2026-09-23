from fastapi import HTTPException

import pytest

from app.domains.products.taxonomy import validate_product_tax


@pytest.mark.asyncio
async def test_product_tax_validation_accepts_local_gst_slab_catalog():
    await validate_product_tax("7318", 18)


@pytest.mark.asyncio
async def test_product_tax_validation_rejects_invalid_hsn():
    with pytest.raises(HTTPException) as exc:
        await validate_product_tax("Demo", 18)
    assert exc.value.status_code == 422


@pytest.mark.asyncio
async def test_product_tax_validation_rejects_invalid_gst_slab():
    with pytest.raises(HTTPException) as exc:
        await validate_product_tax("7318", 17)
    assert exc.value.status_code == 422
