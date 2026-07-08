-- embeddings-doc-and-tags rollback
-- depends: 20260630_01_query-analytics-indexes

DROP TABLE IF EXISTS base.embedding_cache;

ALTER TABLE doc.tag DROP COLUMN IF EXISTS embedding;

ALTER TABLE doc."index"  DROP COLUMN IF EXISTS embedding;
ALTER TABLE doc."column" DROP COLUMN IF EXISTS embedding;
ALTER TABLE doc."table"  DROP COLUMN IF EXISTS embedding;
ALTER TABLE doc.schema   DROP COLUMN IF EXISTS embedding;
ALTER TABLE doc.database DROP COLUMN IF EXISTS embedding;
