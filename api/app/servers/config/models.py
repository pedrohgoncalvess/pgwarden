from datetime import datetime
from enum import Enum
from typing import List, Optional

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


class RunType(str, Enum):
    SERVER = "server"
    DATABASE = "database"


class RunStatus(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"


class RunAction(str, Enum):
    PAUSE = "pause"
    RESUME = "resume"
    STOP = "stop"
    DELETE = "delete"


class RunItem(BaseModel):
    id: int
    server_id: int
    database_id: Optional[int] = None
    database_name: Optional[str] = None
    name: str
    type: RunType
    interval: float
    is_paused: bool
    next_run_at: Optional[datetime] = None
    status: RunStatus

    model_config = ConfigDict(from_attributes=True)


class RunPatch(BaseModel):
    action: RunAction


class RunHistoryItem(BaseModel):
    id: int
    config_id: Optional[int] = None
    database_id: Optional[int] = None
    database_name: Optional[str] = None
    name: Optional[str] = None
    type: Optional[RunType] = None
    status: str
    errors: List[str]
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class RunControlResult(BaseModel):
    id: int
    server_id: int
    database_id: Optional[int] = None
    name: str
    type: RunType
    interval: float
    is_paused: bool
    next_run_at: Optional[datetime] = None
    status: RunStatus
    action: RunAction

    model_config = ConfigDict(from_attributes=True)
