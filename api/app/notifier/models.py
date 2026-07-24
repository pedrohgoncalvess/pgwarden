from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator


class ThresholdResponse(BaseModel):
    id: int
    rule_id: int
    scope: str
    type: str
    entity_id: Optional[int] = None
    entity_public_id: Optional[UUID] = None
    warning: float
    critical: float
    direction: str

    model_config = ConfigDict(from_attributes=True)


class ThresholdPatch(BaseModel):
    warning: Optional[float] = None
    critical: Optional[float] = None
    direction: Optional[str] = None

    @field_validator("direction")
    @classmethod
    def _validate_direction(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        if value not in {"above", "below"}:
            raise ValueError("direction must be 'above' or 'below'")
        return value


class ThresholdCreate(BaseModel):
    scope: str
    type: str
    entity_public_id: Optional[UUID] = None
    warning: float
    critical: float
    direction: str = "above"

    @field_validator("direction")
    @classmethod
    def _validate_direction(cls, value: str) -> str:
        if value not in {"above", "below"}:
            raise ValueError("direction must be 'above' or 'below'")
        return value


class RuleResponse(BaseModel):
    id: int
    name: str
    interval_seconds: float
    cooldown_seconds: float
    window_minutes: float
    enabled: bool
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    thresholds: List[ThresholdResponse] = []

    model_config = ConfigDict(from_attributes=True)


class RulePatch(BaseModel):
    interval_seconds: Optional[float] = None
    cooldown_seconds: Optional[float] = None
    window_minutes: Optional[float] = None
    enabled: Optional[bool] = None


class RuleCreate(BaseModel):
    name: str
    interval_seconds: float = 60
    cooldown_seconds: float = 1800
    window_minutes: float = 5
    enabled: bool = True


class ChannelResponse(BaseModel):
    id: int
    name: str
    enabled: bool
    has_credentials: bool

    model_config = ConfigDict(from_attributes=True)


class ChannelPatch(BaseModel):
    enabled: Optional[bool] = None
    credentials: Optional[Dict[str, Any]] = None
