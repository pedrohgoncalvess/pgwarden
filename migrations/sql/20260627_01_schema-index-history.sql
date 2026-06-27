-- depends: 20260324_01_pUn2z

-- Audit table for index changes. Captures the previous state of an index row
-- before an update that changes any tracked attribute.
CREATE TABLE "metadata"."index_history" (
    id           BIGINT NOT NULL GENERATED ALWAYS AS IDENTITY,
    index_id     BIGINT NOT NULL,
    table_id     BIGINT NOT NULL,
    index_oid    OID NOT NULL,
    name         TEXT NOT NULL,
    type         TEXT NOT NULL,
    definition   TEXT NOT NULL,
    is_unique    BOOLEAN NOT NULL,
    is_primary   BOOLEAN NOT NULL,
    changed_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    changed_by   BIGINT,

    CONSTRAINT index_history_pk PRIMARY KEY (id),
    CONSTRAINT index_history_index_fk FOREIGN KEY (index_id) REFERENCES "metadata"."index"(id) ON DELETE CASCADE,
    CONSTRAINT index_history_table_fk FOREIGN KEY (table_id) REFERENCES "metadata"."table"(id) ON DELETE CASCADE
);

CREATE INDEX ix_index_history_index_id ON "metadata"."index_history" (index_id);
CREATE INDEX ix_index_history_table_id ON "metadata"."index_history" (table_id);

COMMENT ON TABLE "metadata"."index_history" IS 'Audit log of all changes to an index. One row per change, capturing the state before the update.';
COMMENT ON COLUMN "metadata"."index_history".index_id IS 'References the original metadata.index.id that was modified.';
COMMENT ON COLUMN "metadata"."index_history".changed_at IS 'Timestamp when the change was detected by the collector.';
COMMENT ON COLUMN "metadata"."index_history".changed_by IS 'ID of the user or process that triggered the change.';

-- Trigger function that stores the OLD index state before an update.
CREATE OR REPLACE FUNCTION "metadata"."fn_index_history"()
    RETURNS TRIGGER
    LANGUAGE plpgsql
    AS $$
    BEGIN
        INSERT INTO "metadata"."index_history" (
            index_id, table_id, index_oid, name, type, definition, is_unique, is_primary, changed_at, changed_by
        ) VALUES (
            OLD.id, OLD.table_id, OLD.oid, OLD.name, OLD.type, OLD.definition, OLD.is_unique, OLD.is_primary,
            now(), OLD.updated_by
        );
        RETURN NEW;
    END;
$$;

CREATE TRIGGER trg_index_history
    BEFORE UPDATE ON "metadata"."index"
        FOR EACH ROW
            WHEN (
                OLD.name IS DISTINCT FROM NEW.name OR
                OLD.type IS DISTINCT FROM NEW.type OR
                OLD.definition IS DISTINCT FROM NEW.definition OR
                OLD.is_unique IS DISTINCT FROM NEW.is_unique OR
                OLD.is_primary IS DISTINCT FROM NEW.is_primary
            )
EXECUTE FUNCTION "metadata"."fn_index_history"();

-- Recreate table/column history triggers so that soft deletes (deleted_at changes)
-- are also recorded in their respective audit tables.
DROP TRIGGER IF EXISTS trg_table_history ON "metadata"."table";
CREATE TRIGGER trg_table_history
    BEFORE UPDATE ON "metadata"."table"
        FOR EACH ROW
            WHEN (
                OLD.oid IS DISTINCT FROM NEW.oid OR
                OLD.schema_name IS DISTINCT FROM NEW.schema_name OR
                OLD.name IS DISTINCT FROM NEW.name OR
                OLD.description IS DISTINCT FROM NEW.description OR
                OLD.deleted_at IS DISTINCT FROM NEW.deleted_at
            )
EXECUTE FUNCTION "metadata"."fn_table_history"();

DROP TRIGGER IF EXISTS trg_column_history ON "metadata"."column";
CREATE TRIGGER trg_column_history
    BEFORE UPDATE ON "metadata"."column"
        FOR EACH ROW
            WHEN (
                OLD.name IS DISTINCT FROM NEW.name OR
                OLD.description IS DISTINCT FROM NEW.description OR
                OLD.data_type IS DISTINCT FROM NEW.data_type OR
                OLD.is_nullable IS DISTINCT FROM NEW.is_nullable OR
                OLD.default_value IS DISTINCT FROM NEW.default_value OR
                OLD.is_unique IS DISTINCT FROM NEW.is_unique OR
                OLD.ordinal_position IS DISTINCT FROM NEW.ordinal_position OR
                OLD.fk_table_id IS DISTINCT FROM NEW.fk_table_id OR
                OLD.fk_column_id IS DISTINCT FROM NEW.fk_column_id OR
                OLD.deleted_at IS DISTINCT FROM NEW.deleted_at
            )
EXECUTE FUNCTION "metadata"."fn_column_history"();
