from __future__ import annotations

from typing import Any

from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.types import String

from app.metadata.search.models import MetadataSearchResponse, MetadataSearchResult
from utils import decrypt_or_plain
from utils.embeddings import generate_embedding_cached


def _vector_literal(embedding: list[float] | None) -> str | None:
    if embedding is None:
        return None
    return "[" + ",".join(str(value) for value in embedding) + "]"


def _vector_score(column: str, has_embedding: bool) -> str:
    if not has_embedding:
        return "0.0"
    return f"CASE WHEN {column} IS NULL THEN 0.0 ELSE 1.0 / (1.0 + ({column} <-> CAST(:query_embedding AS vector))) END"


def _text_score(name_expression: str, type_expression: str | None = None) -> tuple[str, str]:
    exact_terms = [
        f"CASE WHEN lower({name_expression}) = :query_lower THEN 1.0 ELSE 0.0 END",
        f"CASE WHEN lower({name_expression}) LIKE :query_like THEN 0.75 ELSE 0.0 END",
    ]
    if type_expression:
        exact_terms.append(f"CASE WHEN lower({type_expression}) = :query_lower THEN 0.9 ELSE 0.0 END")

    exact_score = f"GREATEST({', '.join(exact_terms)})"
    fuzzy_score = (
        f"CASE WHEN {name_expression} IS NULL OR :query_lower = '' THEN 0.0 "
        f"ELSE GREATEST(0.0, 1.0 - (levenshtein(left(lower({name_expression}), 255), left(:query_lower, 255))::float "
        f"/ GREATEST(length({name_expression}), length(:query_lower), 1))) END"
    )
    return exact_score, fuzzy_score


_TYPE_KEYWORDS: dict[str, set[str]] = {
    "database": {"database", "databases", "banco", "bancos", "db"},
    "schema": {"schema", "schemas", "esquema", "esquemas"},
    "table": {"table", "tables", "tabela", "tabelas"},
    "column": {"column", "columns", "coluna", "colunas"},
    "index": {"index", "indexes", "indices", "índice", "índices"},
    "tag": {"tag", "tags", "etiqueta", "etiquetas"},
}


_TYPE_BOOST = 0.15


def _extract_boosted_types(query: str) -> set[str]:
    words = {w.lower() for w in query.split()}
    boosted: set[str] = set()
    for object_type, keywords in _TYPE_KEYWORDS.items():
        if words & keywords:
            boosted.add(object_type)
    return boosted


async def search_metadata(
    db: AsyncSession,
    query: str,
    database_id: str | None = None,
    server_id: str | None = None,
    limit: int = 25,
    semantic: bool = True,
) -> MetadataSearchResponse:
    term = " ".join(query.strip().split())
    if semantic:
        embedding = await generate_embedding_cached(db, term)
        embedding_literal = _vector_literal(embedding)
        has_embedding = embedding_literal is not None
    else:
        embedding_literal = None
        has_embedding = False

    db_exact, db_fuzzy = _text_score("db.db_name")
    schema_exact, schema_fuzzy = _text_score("schema_meta.schema_name")
    table_exact, table_fuzzy = _text_score("tbl.name")
    column_exact, column_fuzzy = _text_score("col.name", "col.data_type")
    index_exact, index_fuzzy = _text_score("idx.name", "idx.type")
    tag_exact, tag_fuzzy = _text_score("tag.name", "tag.type")

    sql = text(
        f"""
        WITH candidates AS (
            SELECT
                'database' AS type,
                db.public_id::text AS id,
                db.public_id::text AS database_id,
                db.db_name AS database_name,
                NULL::text AS schema_name,
                NULL::text AS table_id,
                NULL::text AS table_name,
                db.db_name AS name,
                'Database documentation' AS subtitle,
                db_doc.description AS description,
                {db_exact} AS exact_score,
                {db_fuzzy} AS fuzzy_score,
                {_vector_score("db_doc.embedding", has_embedding)} AS vector_score
            FROM metadata.database db
            JOIN collector.server srv ON srv.id = db.server_id
            LEFT JOIN doc.database db_doc ON db_doc.database_id = db.id
            WHERE (:database_id IS NULL OR db.public_id::text = :database_id)
              AND (:server_id IS NULL OR srv.public_id::text = :server_id)

            UNION ALL

            SELECT
                'schema' AS type,
                schema_meta.database_public_id || ':' || schema_meta.schema_name AS id,
                schema_meta.database_public_id AS database_id,
                schema_meta.database_name,
                schema_meta.schema_name,
                NULL::text AS table_id,
                NULL::text AS table_name,
                schema_meta.schema_name AS name,
                'Schema documentation' AS subtitle,
                schema_doc.description AS description,
                {schema_exact} AS exact_score,
                {schema_fuzzy} AS fuzzy_score,
                {_vector_score("schema_doc.embedding", has_embedding)} AS vector_score
            FROM (
                SELECT
                    db.id AS database_internal_id,
                    db.public_id::text AS database_public_id,
                    db.db_name AS database_name,
                    tbl.schema_name,
                    db.server_id
                FROM metadata."table" tbl
                JOIN metadata.database db ON db.id = tbl.database_id
                WHERE tbl.deleted_at IS NULL
                GROUP BY db.id, db.public_id, db.db_name, tbl.schema_name, db.server_id
            ) schema_meta
            JOIN collector.server srv ON srv.id = schema_meta.server_id
            LEFT JOIN doc.schema schema_doc
                ON schema_doc.database_id = schema_meta.database_internal_id
               AND schema_doc.schema_name = schema_meta.schema_name
            WHERE (:database_id IS NULL OR schema_meta.database_public_id = :database_id)
              AND (:server_id IS NULL OR srv.public_id::text = :server_id)

            UNION ALL

            SELECT
                'table' AS type,
                tbl.public_id::text AS id,
                db.public_id::text AS database_id,
                db.db_name AS database_name,
                tbl.schema_name,
                tbl.public_id::text AS table_id,
                tbl.name AS table_name,
                tbl.name AS name,
                tbl.schema_name || '.' || tbl.name AS subtitle,
                table_doc.description AS description,
                {table_exact} AS exact_score,
                {table_fuzzy} AS fuzzy_score,
                {_vector_score("table_doc.embedding", has_embedding)} AS vector_score
            FROM metadata."table" tbl
            JOIN metadata.database db ON db.id = tbl.database_id
            JOIN collector.server srv ON srv.id = db.server_id
            LEFT JOIN doc."table" table_doc ON table_doc.table_id = tbl.id
            WHERE (:database_id IS NULL OR db.public_id::text = :database_id)
              AND (:server_id IS NULL OR srv.public_id::text = :server_id)
              AND tbl.deleted_at IS NULL

            UNION ALL

            SELECT
                'column' AS type,
                col.public_id::text AS id,
                db.public_id::text AS database_id,
                db.db_name AS database_name,
                tbl.schema_name,
                tbl.public_id::text AS table_id,
                tbl.name AS table_name,
                col.name AS name,
                tbl.schema_name || '.' || tbl.name || ' · ' || col.data_type AS subtitle,
                column_doc.description AS description,
                {column_exact} AS exact_score,
                {column_fuzzy} AS fuzzy_score,
                {_vector_score("column_doc.embedding", has_embedding)} AS vector_score
            FROM metadata."column" col
            JOIN metadata."table" tbl ON tbl.id = col.table_id
            JOIN metadata.database db ON db.id = tbl.database_id
            JOIN collector.server srv ON srv.id = db.server_id
            LEFT JOIN doc."column" column_doc ON column_doc.column_id = col.id
            WHERE (:database_id IS NULL OR db.public_id::text = :database_id)
              AND (:server_id IS NULL OR srv.public_id::text = :server_id)
              AND col.deleted_at IS NULL
              AND tbl.deleted_at IS NULL

            UNION ALL

            SELECT
                'index' AS type,
                idx.public_id::text AS id,
                db.public_id::text AS database_id,
                db.db_name AS database_name,
                tbl.schema_name,
                tbl.public_id::text AS table_id,
                tbl.name AS table_name,
                idx.name AS name,
                tbl.schema_name || '.' || tbl.name || ' · ' || idx.type AS subtitle,
                index_doc.description AS description,
                {index_exact} AS exact_score,
                {index_fuzzy} AS fuzzy_score,
                {_vector_score("index_doc.embedding", has_embedding)} AS vector_score
            FROM metadata."index" idx
            JOIN metadata."table" tbl ON tbl.id = idx.table_id
            JOIN metadata.database db ON db.id = idx.database_id
            JOIN collector.server srv ON srv.id = db.server_id
            LEFT JOIN doc."index" index_doc ON index_doc.index_id = idx.id
            WHERE (:database_id IS NULL OR db.public_id::text = :database_id)
              AND (:server_id IS NULL OR srv.public_id::text = :server_id)
              AND idx.deleted_at IS NULL
              AND tbl.deleted_at IS NULL

            UNION ALL

            SELECT
                'tag' AS type,
                tag.public_id::text AS id,
                NULL::text AS database_id,
                NULL::text AS database_name,
                NULL::text AS schema_name,
                NULL::text AS table_id,
                NULL::text AS table_name,
                tag.name AS name,
                tag.type AS subtitle,
                tag.description AS description,
                {tag_exact} AS exact_score,
                {tag_fuzzy} AS fuzzy_score,
                {_vector_score("tag.embedding", has_embedding)} AS vector_score
            FROM doc.tag tag
            JOIN collector.server srv ON srv.id = tag.server_id
            WHERE (:server_id IS NULL OR srv.public_id::text = :server_id)
              AND (
                :database_id IS NULL OR tag.server_id = (
                    SELECT filtered_db.server_id
                    FROM metadata.database filtered_db
                    WHERE filtered_db.public_id::text = :database_id
                    LIMIT 1
                )
              )
        )
        SELECT
            *,
            ((exact_score * 0.45) + (fuzzy_score * 0.25) + (vector_score * 0.30)) AS score
        FROM candidates
        WHERE exact_score > 0 OR fuzzy_score >= 0.55 OR vector_score > 0
        ORDER BY score DESC, exact_score DESC, fuzzy_score DESC
        LIMIT :limit
        """
    ).bindparams(
        bindparam("database_id", type_=String),
        bindparam("server_id", type_=String)
    )

    params: dict[str, Any] = {
        "query_lower": term.lower(),
        "query_like": f"%{term.lower()}%",
        "query_embedding": embedding_literal,
        "database_id": database_id,
        "server_id": server_id,
        "limit": limit,
    }
    rows = (await db.execute(sql, params)).mappings().all()

    boosted_types = _extract_boosted_types(query)

    results = []
    for row in rows:
        item = dict(row)
        if item.get("database_name"):
            item["database_name"] = decrypt_or_plain(item["database_name"])
            if item["type"] == "database":
                item["name"] = item["database_name"]
        if boosted_types and item["type"] in boosted_types:
            item["score"] = min(item["score"] + _TYPE_BOOST, 1.0)
        results.append(MetadataSearchResult(**item))

    if boosted_types:
        results.sort(key=lambda result: result.score, reverse=True)

    return MetadataSearchResponse(query=term, results=results)
