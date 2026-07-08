from uuid import UUID
from typing import List

from fastapi import HTTPException
from sqlalchemy import and_, delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.tags.embeddings import build_tag_embedding_text
from app.tags.models import TagAssignmentCreate, TagAssignmentDelete, TagCreate, TagUpdate
from database.models.doc.column import ColumnDoc
from database.models.doc.database import DatabaseDoc
from database.models.doc.index import IndexDoc
from database.models.doc.object_tag import (
    ColumnTag,
    ColumnDocTag,
    DatabaseTag,
    DatabaseDocTag,
    IndexTag,
    IndexDocTag,
    QueryTag,
    SchemaDocTag,
    TableTag,
    TableDocTag,
)
from database.models.doc.schema import SchemaDoc
from database.models.doc.table import TableDoc
from database.models.doc.tag import Tag
from database.models.metadata.column import ColumnModel
from database.models.metadata.database import Database
from database.models.metadata.index import Index
from database.models.metadata.table import Table
from database.operations.collector.server import ServerRepository
from database.operations.metadata.tag import TagRepository
from utils import decrypt_or_plain
from utils.embeddings import generate_embedding_cached


async def create_tag(db: AsyncSession, tag_in: TagCreate) -> Tag:
    tag_repo = TagRepository(db)
    server = await ServerRepository(db).find_one_by(public_id=tag_in.server_id)
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")

    existing = await tag_repo.find_one_by(server_id=server.id, name=tag_in.name)
    if existing:
        raise HTTPException(status_code=409, detail=f"Tag '{tag_in.name}' already exists for this server")

    embedding_text = build_tag_embedding_text(tag_in)
    embedding = await generate_embedding_cached(db, embedding_text)

    new_tag = Tag(
        server_id=server.id,
        name=tag_in.name,
        description=tag_in.description,
        color=tag_in.color,
        type=tag_in.type,
        embedding=embedding,
    )

    try:
        return await tag_repo.insert(new_tag)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


async def list_tags(db: AsyncSession, server_id: UUID | None = None) -> List[Tag]:
    tag_repo = TagRepository(db)
    if not server_id:
        return await tag_repo.find_all(limit=1000)

    server = await ServerRepository(db).find_one_by(public_id=server_id)
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")
    return await tag_repo.find_by(server_id=server.id)


async def update_tag(db: AsyncSession, tag_id: UUID, tag_in: TagUpdate) -> Tag:
    tag_repo = TagRepository(db)

    tag = await tag_repo.find_one_by(public_id=tag_id)
    if not tag:
        raise HTTPException(status_code=404, detail="Tag not found")

    if tag_in.name and tag_in.name != tag.name:
        existing = await tag_repo.find_one_by(server_id=tag.server_id, name=tag_in.name)
        if existing:
            raise HTTPException(status_code=409, detail=f"Tag '{tag_in.name}' already exists for this server")

    update_data = tag_in.model_dump(exclude_unset=True)
    if not update_data:
        return tag

    # Apply pending changes to a transient copy to build the embedding text.
    pending_name = update_data.get("name", tag.name)
    pending_description = update_data.get("description", tag.description)
    pending_type = update_data.get("type", tag.type)
    embedding_text = build_tag_embedding_text(tag)
    if pending_name != tag.name or pending_description != tag.description or pending_type != tag.type:
        embedding_text = build_tag_embedding_text(_transient_tag(pending_name, pending_description, pending_type))

    embedding = await generate_embedding_cached(db, embedding_text)
    if embedding is not None:
        update_data["embedding"] = embedding

    updated = await tag_repo.update(tag.id, update_data)
    if not updated:
        raise HTTPException(status_code=404, detail="Tag not found")
    return updated


def _transient_tag(name: str, description: str | None, type: str) -> Tag:
    """Return an unsaved Tag instance used only to build an embedding text."""
    return Tag(name=name, description=description, type=type)


async def delete_tag(db: AsyncSession, tag_id: UUID) -> None:
    tag_repo = TagRepository(db)

    tag = await tag_repo.find_one_by(public_id=tag_id)
    if not tag:
        raise HTTPException(status_code=404, detail="Tag not found")

    await tag_repo.delete(tag.id)


async def attach_tag(db: AsyncSession, tag_id: UUID, assignment: TagAssignmentCreate) -> None:
    tag = await _get_tag(db, tag_id)
    model, values = await _resolve_assignment(db, assignment)
    target_server_id = await _resolve_assignment_server_id(db, assignment)
    if target_server_id != tag.server_id:
        raise HTTPException(status_code=400, detail="Tag and target must belong to the same server")
    existing = await _find_assignment(db, model, values, tag.id)
    if existing:
        return

    db.add(model(tag_id=tag.id, **values))
    await db.commit()


async def detach_tag(db: AsyncSession, tag_id: UUID, assignment: TagAssignmentDelete) -> None:
    tag = await _get_tag(db, tag_id)
    model, values = await _resolve_assignment(db, assignment)
    target_server_id = await _resolve_assignment_server_id(db, assignment)
    if target_server_id != tag.server_id:
        raise HTTPException(status_code=400, detail="Tag and target must belong to the same server")
    filters = [getattr(model, key) == value for key, value in values.items()]
    filters.append(model.tag_id == tag.id)
    await db.execute(delete(model).where(and_(*filters)))
    await db.commit()


async def list_assignments(db: AsyncSession, database_id: UUID | None = None) -> list[dict]:
    database = None
    if database_id:
        database = await _get_database(db, database_id)

    assignments: list[dict] = []
    assignments.extend(await _list_database_object_assignments(db, database))
    assignments.extend(await _list_table_object_assignments(db, database))
    assignments.extend(await _list_column_object_assignments(db, database))
    assignments.extend(await _list_index_object_assignments(db, database))
    assignments.extend(await _list_native_query_object_assignments(db, database))
    assignments.extend(await _list_database_doc_assignments(db, database))
    assignments.extend(await _list_schema_doc_assignments(db, database))
    assignments.extend(await _list_table_doc_assignments(db, database))
    assignments.extend(await _list_column_doc_assignments(db, database))
    assignments.extend(await _list_index_doc_assignments(db, database))
    return assignments


async def _get_tag(db: AsyncSession, tag_id: UUID) -> Tag:
    tag = await TagRepository(db).find_one_by(public_id=tag_id)
    if not tag:
        raise HTTPException(status_code=404, detail="Tag not found")
    return tag


async def _get_database(db: AsyncSession, public_id: UUID) -> Database:
    result = await db.execute(
        select(Database).where(Database.public_id == public_id, Database.deleted_at.is_(None))
    )
    database = result.scalar_one_or_none()
    if not database:
        raise HTTPException(status_code=404, detail="Database not found")
    return database


async def _get_table(db: AsyncSession, public_id: UUID) -> Table:
    result = await db.execute(select(Table).where(Table.public_id == public_id, Table.deleted_at.is_(None)))
    table = result.scalar_one_or_none()
    if not table:
        raise HTTPException(status_code=404, detail="Table not found")
    return table


async def _get_column(db: AsyncSession, public_id: UUID) -> ColumnModel:
    result = await db.execute(
        select(ColumnModel).where(ColumnModel.public_id == public_id, ColumnModel.deleted_at.is_(None))
    )
    column = result.scalar_one_or_none()
    if not column:
        raise HTTPException(status_code=404, detail="Column not found")
    return column


async def _get_index(db: AsyncSession, public_id: UUID) -> Index:
    result = await db.execute(select(Index).where(Index.public_id == public_id, Index.deleted_at.is_(None)))
    index = result.scalar_one_or_none()
    if not index:
        raise HTTPException(status_code=404, detail="Index not found")
    return index


async def _get_database_by_id(db: AsyncSession, id: int) -> Database:
    result = await db.execute(select(Database).where(Database.id == id, Database.deleted_at.is_(None)))
    database = result.scalar_one_or_none()
    if not database:
        raise HTTPException(status_code=404, detail="Database not found")
    return database


async def _resolve_assignment_server_id(db: AsyncSession, assignment: TagAssignmentCreate) -> int:
    if assignment.target_type == "database":
        target_id = assignment.target_id or assignment.database_id
        if not target_id:
            raise HTTPException(status_code=400, detail="target_id or database_id is required")
        return (await _get_database(db, target_id)).server_id

    if assignment.target_type == "schema":
        if not assignment.database_id:
            raise HTTPException(status_code=400, detail="database_id is required")
        return (await _get_database(db, assignment.database_id)).server_id

    if assignment.target_type == "table":
        if not assignment.target_id:
            raise HTTPException(status_code=400, detail="target_id is required")
        table = await _get_table(db, assignment.target_id)
        return (await _get_database_by_id(db, table.database_id)).server_id

    if assignment.target_type == "column":
        if not assignment.target_id:
            raise HTTPException(status_code=400, detail="target_id is required")
        column = await _get_column(db, assignment.target_id)
        table = await _get_table_by_id(db, column.table_id)
        return (await _get_database_by_id(db, table.database_id)).server_id

    if assignment.target_type == "index":
        if not assignment.target_id:
            raise HTTPException(status_code=400, detail="target_id is required")
        index = await _get_index(db, assignment.target_id)
        return (await _get_database_by_id(db, index.database_id)).server_id

    if assignment.target_type == "native_query":
        if not assignment.database_id:
            raise HTTPException(status_code=400, detail="database_id is required")
        return (await _get_database(db, assignment.database_id)).server_id

    raise HTTPException(status_code=400, detail="Invalid target type")


async def _get_table_by_id(db: AsyncSession, id: int) -> Table:
    result = await db.execute(select(Table).where(Table.id == id, Table.deleted_at.is_(None)))
    table = result.scalar_one_or_none()
    if not table:
        raise HTTPException(status_code=404, detail="Table not found")
    return table


async def _resolve_assignment(db: AsyncSession, assignment: TagAssignmentCreate):
    if assignment.scope == "object":
        return await _resolve_object_assignment(db, assignment)
    if assignment.scope == "doc":
        return await _resolve_doc_assignment(db, assignment)
    raise HTTPException(status_code=400, detail="Invalid tag assignment scope")


async def _resolve_object_assignment(db: AsyncSession, assignment: TagAssignmentCreate):
    if assignment.target_type == "database":
        if not assignment.target_id:
            raise HTTPException(status_code=400, detail="target_id is required")
        database = await _get_database(db, assignment.target_id)
        return DatabaseTag, {"database_id": database.id}

    if assignment.target_type == "table":
        if not assignment.target_id:
            raise HTTPException(status_code=400, detail="target_id is required")
        table = await _get_table(db, assignment.target_id)
        return TableTag, {"table_id": table.id}

    if assignment.target_type == "column":
        if not assignment.target_id:
            raise HTTPException(status_code=400, detail="target_id is required")
        column = await _get_column(db, assignment.target_id)
        return ColumnTag, {"column_id": column.id}

    if assignment.target_type == "index":
        if not assignment.target_id:
            raise HTTPException(status_code=400, detail="target_id is required")
        index = await _get_index(db, assignment.target_id)
        return IndexTag, {"index_id": index.id}

    if assignment.target_type == "native_query":
        if not assignment.database_id or not assignment.query_hash:
            raise HTTPException(status_code=400, detail="database_id and query_hash are required")
        database = await _get_database(db, assignment.database_id)
        return QueryTag, {"database_id": database.id, "query_hash": assignment.query_hash}

    raise HTTPException(status_code=400, detail="Invalid object target type")


async def _resolve_doc_assignment(db: AsyncSession, assignment: TagAssignmentCreate):
    if assignment.target_type == "database":
        if not assignment.target_id:
            raise HTTPException(status_code=400, detail="target_id is required")
        database = await _get_database(db, assignment.target_id)
        doc = await _get_or_create_doc(db, DatabaseDoc, database_id=database.id)
        return DatabaseDocTag, {"database_doc_id": doc.id}

    if assignment.target_type == "schema":
        if not assignment.database_id or not assignment.schema_name:
            raise HTTPException(status_code=400, detail="database_id and schema_name are required")
        database = await _get_database(db, assignment.database_id)
        doc = await _get_or_create_doc(db, SchemaDoc, database_id=database.id, schema_name=assignment.schema_name)
        return SchemaDocTag, {"schema_doc_id": doc.id}

    if assignment.target_type == "table":
        if not assignment.target_id:
            raise HTTPException(status_code=400, detail="target_id is required")
        table = await _get_table(db, assignment.target_id)
        doc = await _get_or_create_doc(db, TableDoc, table_id=table.id)
        return TableDocTag, {"table_doc_id": doc.id}

    if assignment.target_type == "column":
        if not assignment.target_id:
            raise HTTPException(status_code=400, detail="target_id is required")
        column = await _get_column(db, assignment.target_id)
        doc = await _get_or_create_doc(db, ColumnDoc, column_id=column.id)
        return ColumnDocTag, {"column_doc_id": doc.id}

    if assignment.target_type == "index":
        if not assignment.target_id:
            raise HTTPException(status_code=400, detail="target_id is required")
        index = await _get_index(db, assignment.target_id)
        doc = await _get_or_create_doc(db, IndexDoc, index_id=index.id)
        return IndexDocTag, {"index_doc_id": doc.id}

    raise HTTPException(status_code=400, detail="Invalid documentation target type")


async def _get_or_create_doc(db: AsyncSession, model, **values):
    filters = [getattr(model, key) == value for key, value in values.items()]
    result = await db.execute(select(model).where(and_(*filters)))
    doc = result.scalar_one_or_none()
    if doc:
        return doc

    doc = model(**values)
    db.add(doc)
    await db.commit()
    await db.refresh(doc)
    return doc


async def _find_assignment(db: AsyncSession, model, values: dict, tag_id: int):
    filters = [getattr(model, key) == value for key, value in values.items()]
    filters.append(model.tag_id == tag_id)
    result = await db.execute(select(model).where(and_(*filters)))
    return result.scalar_one_or_none()


def _assignment_dict(tag: Tag, scope: str, target_type: str, target_id, target_label: str, created_at, database_id=None, query_hash=None):
    return {
        "tag": tag,
        "scope": scope,
        "target_type": target_type,
        "target_id": str(target_id) if target_id else None,
        "target_label": target_label,
        "database_id": str(database_id) if database_id else None,
        "query_hash": query_hash,
        "created_at": created_at,
    }


async def _list_database_object_assignments(db: AsyncSession, database: Database | None):
    query = (
        select(Tag, DatabaseTag, Database)
        .select_from(DatabaseTag)
        .join(Tag, Tag.id == DatabaseTag.tag_id)
        .join(Database, Database.id == DatabaseTag.database_id)
    )
    if database:
        query = query.where(Database.id == database.id)
    rows = (await db.execute(query)).all()
    return [
        _assignment_dict(tag, "object", "database", target.public_id, decrypt_or_plain(target.db_name), link.created_at, target.public_id)
        for tag, link, target in rows
    ]


async def _list_table_object_assignments(db: AsyncSession, database: Database | None):
    query = (
        select(Tag, TableTag, Table)
        .select_from(TableTag)
        .join(Tag, Tag.id == TableTag.tag_id)
        .join(Table, Table.id == TableTag.table_id)
    )
    if database:
        query = query.where(Table.database_id == database.id)
    rows = (await db.execute(query)).all()
    return [
        _assignment_dict(tag, "object", "table", target.public_id, f"{target.schema_name}.{target.name}", link.created_at)
        for tag, link, target in rows
    ]


async def _list_column_object_assignments(db: AsyncSession, database: Database | None):
    query = (
        select(Tag, ColumnTag, ColumnModel, Table)
        .select_from(ColumnTag)
        .join(Tag, Tag.id == ColumnTag.tag_id)
        .join(ColumnModel, ColumnModel.id == ColumnTag.column_id)
        .join(Table, Table.id == ColumnModel.table_id)
    )
    if database:
        query = query.where(Table.database_id == database.id)
    rows = (await db.execute(query)).all()
    return [
        _assignment_dict(tag, "object", "column", column.public_id, f"{table.schema_name}.{table.name}.{column.name}", link.created_at)
        for tag, link, column, table in rows
    ]


async def _list_index_object_assignments(db: AsyncSession, database: Database | None):
    query = (
        select(Tag, IndexTag, Index)
        .select_from(IndexTag)
        .join(Tag, Tag.id == IndexTag.tag_id)
        .join(Index, Index.id == IndexTag.index_id)
    )
    if database:
        query = query.where(Index.database_id == database.id)
    rows = (await db.execute(query)).all()
    return [
        _assignment_dict(tag, "object", "index", target.public_id, target.name, link.created_at)
        for tag, link, target in rows
    ]


async def _list_native_query_object_assignments(db: AsyncSession, database: Database | None):
    query = (
        select(Tag, QueryTag, Database)
        .select_from(QueryTag)
        .join(Tag, Tag.id == QueryTag.tag_id)
        .join(Database, Database.id == QueryTag.database_id)
    )
    if database:
        query = query.where(Database.id == database.id)
    rows = (await db.execute(query)).all()
    return [
        _assignment_dict(tag, "object", "native_query", None, link.query_hash, link.created_at, target.public_id, link.query_hash)
        for tag, link, target in rows
    ]


async def _list_database_doc_assignments(db: AsyncSession, database: Database | None):
    query = (
        select(Tag, DatabaseDocTag, DatabaseDoc, Database)
        .select_from(DatabaseDocTag)
        .join(Tag, Tag.id == DatabaseDocTag.tag_id)
        .join(DatabaseDoc, DatabaseDoc.id == DatabaseDocTag.database_doc_id)
        .join(Database, Database.id == DatabaseDoc.database_id)
    )
    if database:
        query = query.where(Database.id == database.id)
    rows = (await db.execute(query)).all()
    return [
        _assignment_dict(tag, "doc", "database", target.public_id, decrypt_or_plain(target.db_name), link.created_at, target.public_id)
        for tag, link, _doc, target in rows
    ]


async def _list_schema_doc_assignments(db: AsyncSession, database: Database | None):
    query = (
        select(Tag, SchemaDocTag, SchemaDoc, Database)
        .select_from(SchemaDocTag)
        .join(Tag, Tag.id == SchemaDocTag.tag_id)
        .join(SchemaDoc, SchemaDoc.id == SchemaDocTag.schema_doc_id)
        .join(Database, Database.id == SchemaDoc.database_id)
    )
    if database:
        query = query.where(Database.id == database.id)
    rows = (await db.execute(query)).all()
    return [
        _assignment_dict(tag, "doc", "schema", None, doc.schema_name, link.created_at, target.public_id)
        for tag, link, doc, target in rows
    ]


async def _list_table_doc_assignments(db: AsyncSession, database: Database | None):
    query = (
        select(Tag, TableDocTag, TableDoc, Table)
        .select_from(TableDocTag)
        .join(Tag, Tag.id == TableDocTag.tag_id)
        .join(TableDoc, TableDoc.id == TableDocTag.table_doc_id)
        .join(Table, Table.id == TableDoc.table_id)
    )
    if database:
        query = query.where(Table.database_id == database.id)
    rows = (await db.execute(query)).all()
    return [
        _assignment_dict(tag, "doc", "table", target.public_id, f"{target.schema_name}.{target.name}", link.created_at)
        for tag, link, _doc, target in rows
    ]


async def _list_column_doc_assignments(db: AsyncSession, database: Database | None):
    query = (
        select(Tag, ColumnDocTag, ColumnDoc, ColumnModel, Table)
        .select_from(ColumnDocTag)
        .join(Tag, Tag.id == ColumnDocTag.tag_id)
        .join(ColumnDoc, ColumnDoc.id == ColumnDocTag.column_doc_id)
        .join(ColumnModel, ColumnModel.id == ColumnDoc.column_id)
        .join(Table, Table.id == ColumnModel.table_id)
    )
    if database:
        query = query.where(Table.database_id == database.id)
    rows = (await db.execute(query)).all()
    return [
        _assignment_dict(tag, "doc", "column", column.public_id, f"{table.schema_name}.{table.name}.{column.name}", link.created_at)
        for tag, link, _doc, column, table in rows
    ]


async def _list_index_doc_assignments(db: AsyncSession, database: Database | None):
    query = (
        select(Tag, IndexDocTag, IndexDoc, Index)
        .select_from(IndexDocTag)
        .join(Tag, Tag.id == IndexDocTag.tag_id)
        .join(IndexDoc, IndexDoc.id == IndexDocTag.index_doc_id)
        .join(Index, Index.id == IndexDoc.index_id)
    )
    if database:
        query = query.where(Index.database_id == database.id)
    rows = (await db.execute(query)).all()
    return [
        _assignment_dict(tag, "doc", "index", target.public_id, target.name, link.created_at)
        for tag, link, _doc, target in rows
    ]
