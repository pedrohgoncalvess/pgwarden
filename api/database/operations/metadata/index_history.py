from database.operations.interface import Interface
from database.models.metadata.index_history import IndexHistory


class IndexHistoryRepository(Interface[IndexHistory]):
    def __init__(self, db):
        super().__init__(IndexHistory, db)
