from fastapi import HTTPException, status
from typing import Any
from app.constants.system_messages import SystemSecurityMessages

def get_pricing_from_config(config: dict[str, Any] | None) -> PricingStrategy:
    """
    Factory — builds strategy strictly from pricing_config DB row.
    🚨 Fails-Fast with HTTP 503 if config is missing.
    """
    if not config:
        logger.error("CRITICAL: Pricing config missing from Database. Rejecting request to prevent financial loss.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=SystemSecurityMessages.PRICING_UNAVAILABLE,
        )

    tax_enabled      = config.get("tax_enabled", True)
    shipping_enabled = config.get("shipping_enabled", True)
    currency         = config.get("currency", "INR")

    tax_rate           = Decimal(str(config.get("tax_rate", 18.0))) / Decimal("100")
    shipping_flat      = Decimal(str(config.get("shipping_flat", 99.0)))
    shipping_threshold = Decimal(str(config.get("shipping_threshold", 999.0)))

    if not tax_enabled:
        return ZeroTaxPricing(
            shipping_threshold=shipping_threshold if shipping_enabled else Decimal("0"),
            shipping_flat=shipping_flat if shipping_enabled else Decimal("0"),
            currency=currency,
        )

    if not shipping_enabled:
        return StandardPricing(
            shipping_threshold=Decimal("0"),
            shipping_flat=Decimal("0"),
            tax_rate=tax_rate,
            currency=currency,
        )

    return StandardPricing(
        shipping_threshold=shipping_threshold,
        shipping_flat=shipping_flat,
        tax_rate=tax_rate,
        currency=currency,
    )