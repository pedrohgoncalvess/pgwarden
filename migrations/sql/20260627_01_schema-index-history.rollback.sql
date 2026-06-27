-- Rollback: restore original table/column triggers and drop index history artifacts.

DROP TRIGGER IF EXISTS trg_index_history ON "metadata"."index";
DROP FUNCTION IF EXISTS "metadata"."fn_index_history"();
DROP TABLE IF EXISTS "metadata"."index_history";

-- Restore original table history trigger (does not include deleted_at).
DROP TRIGGER IF EXISTS trg_table_history ON "metadata"."table";
CREATE TRIGGER trg_table_history
    BEFORE UPDATE ON "metadata"."table"
        FOR EACH ROW
            WHEN (
                OLD.oid IS DISTINCT FROM NEW.oid OR
                OLD.schema_name IS DISTINCT FROM NEW.schema_name OR
                OLD.name IS DISTINCT FROM NEW.name OR
                OLD.description IS DISTINCT FROM NEW.description
            )
EXECUTE FUNCTION "metadata"."fn_table_history"();

-- Restore original column history trigger (does not include deleted_at).
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
                OLD.fk_column_id IS DISTINCT FROM NEW.fk_column_id
            )
EXECUTE FUNCTION "metadata"."fn_column_history"();
