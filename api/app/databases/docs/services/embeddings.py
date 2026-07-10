
from __future__ import annotations

from database.models.doc.column import ColumnDoc
from database.models.doc.database import DatabaseDoc
from database.models.doc.index import IndexDoc
from database.models.doc.schema import SchemaDoc
from database.models.doc.table import TableDoc
from database.models.metadata.column import ColumnModel
from database.models.metadata.database import Database
from database.models.metadata.index import Index
from database.models.metadata.table import Table


def build_database_embedding_text(database: Database, db_name: str, doc: DatabaseDoc) -> str:
    parts = [f"Database: {db_name}"]
    if doc.description:
        parts.append(f"Description: {doc.description}")
    return "\n".join(parts)


def build_schema_embedding_text(database: Database, db_name: str, schema_name: str, doc: SchemaDoc) -> str:
    parts = [f"Schema: {schema_name}", f"Database: {db_name}"]
    if doc.description:
        parts.append(f"Description: {doc.description}")
    return "\n".join(parts)


def build_table_embedding_text(table: Table, columns: list[ColumnModel], doc: TableDoc) -> str:
    parts = [f"Table: {table.schema_name}.{table.name}"]

    if columns:
        col_summary = ", ".join(
            f"{col.name} ({col.data_type})" for col in columns if not col.deleted_at
        )
        parts.append(f"Columns: {col_summary}")

    if doc.description:
        parts.append(f"Description: {doc.description}")
    return "\n".join(parts)


def build_column_embedding_text(column: ColumnModel, table: Table, doc: ColumnDoc) -> str:
    parts = [
        f"Column: {table.schema_name}.{table.name}.{column.name}",
        f"Type: {column.data_type}",
    ]
    if not column.is_nullable:
        parts.append("Nullable: false")
    if column.is_unique:
        parts.append("Unique: true")
    if column.default_value:
        parts.append(f"Default: {column.default_value}")
    if doc.is_pii:
        parts.append("Contains PII")
    if doc.sample_values:
        parts.append(f"Sample values: {doc.sample_values}")
    if doc.description:
        parts.append(f"Description: {doc.description}")
    return "\n".join(parts)


def build_index_embedding_text(index: Index, table: Table, doc: IndexDoc) -> str:
    parts = [
        f"Index: {index.name}",
        f"Table: {table.schema_name}.{table.name}",
        f"Type: {index.type}",
        f"Definition: {index.definition}",
    ]
    if index.is_unique:
        parts.append("Unique: true")
    if index.is_primary:
        parts.append("Primary: true")
    if doc.description:
        parts.append(f"Description: {doc.description}")
    return "\n".join(parts)

