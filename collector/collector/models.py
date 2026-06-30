import asyncio
from datetime import datetime
from typing import Callable, Coroutine

import enum
from dataclasses import dataclass, field


class CollectorStatus(enum.StrEnum):
    IDLE    = "idle"
    RUNNING = "running"
    PAUSED  = "paused"
    ERROR   = "error"


@dataclass
class CollectorState:
    name:        str
    interval:    float
    fn:          Callable[[], Coroutine]
    config_id:   int
    status:      CollectorStatus      = CollectorStatus.IDLE
    last_run_at: datetime | None      = None
    last_error:  str | None           = None
    run_count:    int                  = 0
    error_count:  int                  = 0
    is_running:   bool                 = False
    _task:        asyncio.Task | None  = field(default=None,                repr=False)
    _force:       asyncio.Event        = field(default_factory=asyncio.Event, repr=False)
    _paused:      asyncio.Event        = field(default_factory=asyncio.Event, repr=False)

    def __post_init__(self) -> None:
        self._paused.set()