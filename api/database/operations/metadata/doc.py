from database.operations.interface import Interface
from database.models.doc.database import DatabaseDoc
from database.models.doc.schema import SchemaDoc
from database.models.doc.table import TableDoc
from database.models.doc.column import ColumnDoc
from database.models.doc.index import IndexDoc
from database.models.doc.object_tag import (
    DatabaseDocTag, SchemaDocTag, TableDocTag, ColumnDocTag, IndexDocTag,
    DatabaseTag, TableTag, ColumnTag, IndexTag, QueryTag
)


class DatabaseDocRepository(Interface[DatabaseDoc]):
    def __init__(self, db):
        super().__init__(DatabaseDoc, db)

class SchemaDocRepository(Interface[SchemaDoc]):
    def __init__(self, db):
        super().__init__(SchemaDoc, db)

class TableDocRepository(Interface[TableDoc]):
    def __init__(self, db):
        super().__init__(TableDoc, db)

class ColumnDocRepository(Interface[ColumnDoc]):
    def __init__(self, db):
        super().__init__(ColumnDoc, db)

class IndexDocRepository(Interface[IndexDoc]):
    def __init__(self, db):
        super().__init__(IndexDoc, db)


class DatabaseDocTagRepository(Interface[DatabaseDocTag]):
    def __init__(self, db):
        super().__init__(DatabaseDocTag, db)

class SchemaDocTagRepository(Interface[SchemaDocTag]):
    def __init__(self, db):
        super().__init__(SchemaDocTag, db)

class TableDocTagRepository(Interface[TableDocTag]):
    def __init__(self, db):
        super().__init__(TableDocTag, db)

class ColumnDocTagRepository(Interface[ColumnDocTag]):
    def __init__(self, db):
        super().__init__(ColumnDocTag, db)

class IndexDocTagRepository(Interface[IndexDocTag]):
    def __init__(self, db):
        super().__init__(IndexDocTag, db)

class DatabaseTagRepository(Interface[DatabaseTag]):
    def __init__(self, db):
        super().__init__(DatabaseTag, db)

class TableTagRepository(Interface[TableTag]):
    def __init__(self, db):
        super().__init__(TableTag, db)

class ColumnTagRepository(Interface[ColumnTag]):
    def __init__(self, db):
        super().__init__(ColumnTag, db)

class IndexTagRepository(Interface[IndexTag]):
    def __init__(self, db):
        super().__init__(IndexTag, db)

class QueryTagRepository(Interface[QueryTag]):
    def __init__(self, db):
        super().__init__(QueryTag, db)
