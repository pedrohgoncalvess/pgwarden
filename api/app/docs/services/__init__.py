from app.docs.services.common import resolve_object
from app.docs.services.database import put_database_doc, get_database_doc
from app.docs.services.schema import put_schema_doc, get_schema_doc
from app.docs.services.table import put_table_doc, get_table_doc
from app.docs.services.column import put_column_doc, get_column_doc
from app.docs.services.index import put_index_doc, get_index_doc
from app.docs.services.tags import attach_tag, detach_tag


__all__ = [
    "resolve_object",
    "put_database_doc",
    "get_database_doc",
    "put_schema_doc",
    "get_schema_doc",
    "put_table_doc",
    "get_table_doc",
    "put_column_doc",
    "get_column_doc",
    "put_index_doc",
    "get_index_doc",
    "attach_tag",
    "detach_tag",
]
