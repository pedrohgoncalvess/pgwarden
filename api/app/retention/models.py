"""Validated retention requests."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class RetentionWindow(BaseModel):
    """Represent a positive calendar interval supported by PostgreSQL."""

    model_config = ConfigDict(extra="forbid")
    value: int = Field(ge=1, le=100000)
    unit: Literal["minutes", "hours", "days", "weeks", "months"]
