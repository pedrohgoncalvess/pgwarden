import asyncio
from abc import ABC, abstractmethod

from database import DatabaseConnection
from log import logger


class BaseCollector(ABC):

    def __init__(
        self,
        monitored_db: DatabaseConnection,
        metrics_db:   DatabaseConnection,
    ) -> None:
        self.monitored_db = monitored_db
        self.metrics_db   = metrics_db

    async def collect(self) -> None:
        try:
            await self._collect()
        except asyncio.CancelledError:
            raise
        except Exception as error:
            await logger.error(
                self.__class__.__name__,
                "collect",
                f"Unhandled error: {error}",
            )

    @abstractmethod
    async def _collect(self) -> None: ...