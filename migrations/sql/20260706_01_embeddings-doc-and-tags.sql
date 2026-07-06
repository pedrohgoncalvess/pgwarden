-- embeddings-doc-and-tags
-- depends: 20260630_01_query-analytics-indexes

-- The vector extension must already be available in the target cluster.
-- This migration assumes it is enabled (or enables it idempotently).
CREATE EXTENSION IF NOT EXISTS vector;

ALTER TABLE doc.database ADD COLUMN IF NOT EXISTS embedding vector(1024);
ALTER TABLE doc.schema  ADD COLUMN IF NOT EXISTS embedding vector(1024);
ALTER TABLE doc."table" ADD COLUMN IF NOT EXISTS embedding vector(1024);
ALTER TABLE doc."column" ADD COLUMN IF NOT EXISTS embedding vector(1024);
ALTER TABLE doc."index" ADD COLUMN IF NOT EXISTS embedding vector(1024);

ALTER TABLE doc.tag ADD COLUMN IF NOT EXISTS embedding vector(1024);

-- HNSW indexes for fast cosine-similarity search on each documentation embedding.
CREATE INDEX IF NOT EXISTS doc_database_embedding_idx ON doc.database USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS doc_schema_embedding_idx   ON doc.schema   USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS doc_table_embedding_idx    ON doc."table"  USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS doc_column_embedding_idx   ON doc."column" USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS doc_index_embedding_idx    ON doc."index"  USING hnsw (embedding vector_cosine_ops);

-- Tags are optionally embedded (nullable), so only create the index when useful rows exist.
CREATE INDEX IF NOT EXISTS doc_tag_embedding_idx ON doc.tag USING hnsw (embedding vector_cosine_ops);
