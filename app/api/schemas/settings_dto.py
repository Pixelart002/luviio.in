"""
Settings Schemas (DTOs)
=======================
Path: app/api/schemas/settings_dto.py
"""
from pydantic import BaseModel, ConfigDict, Field
from typing import Any, List, Optional
from datetime import datetime
from app.enums.settings import SettingCategory, SettingDataType

class SettingUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    value: Any = Field(..., description="New dynamic value matching the setting's data type")
    reason: Optional[str] = Field(default=None, max_length=255, description="Audit reason for change")

class SettingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    key: str
    category: SettingCategory
    data_type: SettingDataType
    value: Any
    default_value: Any
    description: Optional[str] = None
    is_system_locked: bool
    is_public: bool
    updated_at: Optional[datetime] = None

class SettingListResponse(BaseModel):
    items: List[SettingResponse]
    total: int