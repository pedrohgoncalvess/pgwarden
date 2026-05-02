from database.operations.interface import Interface
from database.models.doc.database import DatabaseDoc
from database.models.doc.schema import SchemaDoc
from database.models.doc.table import TableDoc
from database.models.doc.column import ColumnDoc
from database.models.doc.index import IndexDoc
from database.models.doc.object_tag import DatabaseTag, SchemaTag, TableTag, ColumnTag, IndexTag


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


class DatabaseTagRepository(Interface[DatabaseTag]):
    def __init__(self, db):
        super().__init__(DatabaseTag, db)

class SchemaTagRepository(Interface[SchemaTag]):
    def __init__(self, db):
        super().__init__(SchemaTag, db)

class TableTagRepository(Interface[TableTag]):
    def __init__(self, db):
        super().__init__(TableTag, db)

class ColumnTagRepository(Interface[ColumnTag]):
    def __init__(self, db):
        super().__init__(ColumnTag, db)

class IndexTagRepository(Interface[IndexTag]):
    def __init__(self, db):
        super().__init__(IndexTag, db)
