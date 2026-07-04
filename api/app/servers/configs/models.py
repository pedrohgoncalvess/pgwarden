from typing import Optional

from pydantic import BaseModel, ConfigDict


class ConfigItem(BaseModel):
    id: int
    name: str
    interval: int
    is_paused: bool

    model_config = ConfigDict(from_attributes=True)


class ConfigPatch(BaseModel):
    is_paused: Optional[bool] = None
    interval: Optional[int] = None
