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


class ProcessType(str, Enum):
    SERVER = "server"
    DATABASE = "database"


class ProcessStatus(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"


class ProcessAction(str, Enum):
    PAUSE = "pause"
    RESUME = "resume"
    STOP = "stop"
    DELETE = "delete"


class ProcessItem(BaseModel):
    id: int
    server_id: int
    database_id: Optional[int] = None
    database_name: Optional[str] = None
    name: str
    type: ProcessType
    interval: float
    is_paused: bool
    next_run_at: Optional[datetime] = None
    status: ProcessStatus

    model_config = ConfigDict(from_attributes=True)


class ProcessPatch(BaseModel):
    action: ProcessAction


class ProcessHistoryItem(BaseModel):
    id: int
    config_id: Optional[int] = None
    database_id: Optional[int] = None
    database_name: Optional[str] = None
    name: Optional[str] = None
    type: Optional[ProcessType] = None
    status: str
    errors: List[str]
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class ProcessControlResult(BaseModel):
    id: int
    server_id: int
    database_id: Optional[int] = None
    name: str
    type: ProcessType
    interval: float
    is_paused: bool
    next_run_at: Optional[datetime] = None
    status: ProcessStatus
    action: ProcessAction

    model_config = ConfigDict(from_attributes=True)
