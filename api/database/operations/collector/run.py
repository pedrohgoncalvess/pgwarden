from sqlalchemy import select, desc

from database.operations.interface import Interface
from database.models.collector.run import Run


class RunRepository(Interface[Run]):
    def __init__(self, db):
        super().__init__(Run, db)

    async def find_by_configs(self, config_server_ids: list[int], config_database_ids: list[int], limit: int = 100, offset: int = 0):
        query = select(Run)
        filters = []
        if config_server_ids:
            filters.append(Run.config_server_id.in_(config_server_ids))
        if config_database_ids:
            filters.append(Run.config_database_id.in_(config_database_ids))

        if not filters:
            return []

        query = query.where(*filters).order_by(desc(Run.inserted_at)).offset(offset).limit(limit)
        result = await self.db.execute(query)
        return list(result.scalars().all())
