from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, Field, model_validator


class DimensionUnit(StrEnum):
    CM = "cm"
    IN = "in"


class WeightUnit(StrEnum):
    GRAM = "g"
    KILOGRAM = "kg"


class ProductDimensions(BaseModel):
    length: Decimal = Field(..., gt=0, le=Decimal("500"), decimal_places=2)
    width: Decimal = Field(..., gt=0, le=Decimal("500"), decimal_places=2)
    height: Decimal = Field(..., gt=0, le=Decimal("500"), decimal_places=2)
    unit: DimensionUnit = DimensionUnit.CM

    @property
    def cubic_cm(self) -> Decimal:
        factor = Decimal("2.54") if self.unit == DimensionUnit.IN else Decimal("1")
        return self.length * factor * self.width * factor * self.height * factor


class ProductPackage(BaseModel):
    weight: Decimal = Field(..., gt=0, le=Decimal("100000"), decimal_places=2)
    weight_unit: WeightUnit = WeightUnit.GRAM
    dimensions: ProductDimensions

    @property
    def weight_kg(self) -> Decimal:
        return self.weight / Decimal("1000") if self.weight_unit == WeightUnit.GRAM else self.weight

    @property
    def volumetric_weight_kg(self) -> Decimal:
        return self.dimensions.cubic_cm / Decimal("5000")

    @property
    def chargeable_weight_kg(self) -> Decimal:
        return max(self.weight_kg, self.volumetric_weight_kg)

    @model_validator(mode="after")
    def validate_shipping_package(self):
        if self.chargeable_weight_kg > Decimal("100"):
            raise ValueError("Package chargeable weight cannot exceed 100 kg")
        return self
