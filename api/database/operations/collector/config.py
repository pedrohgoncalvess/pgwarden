from database.operations.interface import Interface
from database.models.collector.config import ConfigDatabase, ConfigServer


class ConfigDatabaseRepository(Interface[ConfigDatabase]):
    def __init__(self, db):
        super().__init__(ConfigDatabase, db)


class ConfigServerRepository(Interface[ConfigServer]):
    def __init__(self, db):
        super().__init__(ConfigServer, db)
