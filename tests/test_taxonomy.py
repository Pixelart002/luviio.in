from unittest.mock import AsyncMock, patch

import pytest

from app.domains.products.taxonomy import search_hsn, validate_product_tax


@pytest.mark.asyncio
async def test_hsn_search_uses_external_provider():
    with patch("app.domains.products.taxonomy.hsn_gst_client.search", new=AsyncMock(return_value=[{"hsn_sac": "7318", "gst_rate": "18%"}])) as mocked:
        result = await search_hsn("bolt")
    assert result[0]["hsn_sac"] == "7318"
    mocked.assert_awaited_once_with("bolt", 8)


@pytest.mark.asyncio
async def test_product_tax_validation_can_be_enforced_without_hardcoded_slabs():
    with patch("app.domains.products.taxonomy.settings.TAXONOMY_ENFORCE_PRODUCT_TAX", True), patch(
        "app.domains.products.taxonomy.hsn_gst_client.validate_product_tax", new=AsyncMock(return_value={})
    ) as mocked:
        await validate_product_tax("7318", 18)
    mocked.assert_awaited_once_with("7318", 18)
