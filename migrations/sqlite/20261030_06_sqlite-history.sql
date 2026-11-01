-- depends: 20261030_05_sqlite-defaults

CREATE TRIGGER history_table BEFORE UPDATE ON metadata_table
WHEN OLD.oid IS NOT NEW.oid
    OR OLD.schema_name IS NOT NEW.schema_name
    OR OLD.name IS NOT NEW.name
    OR OLD.description IS NOT NEW.description
    OR OLD.deleted_at IS NOT NEW.deleted_at
BEGIN
    INSERT INTO metadata_table_history (table_id, table_oid, schema_name, name, description, changed_at, changed_by)
    VALUES (OLD.id, OLD.oid, OLD.schema_name, OLD.name, OLD.description, strftime('%Y-%m-%dT%H:%M:%f+00:00', 'now'), OLD.updated_by);
END;

CREATE TRIGGER history_column BEFORE UPDATE ON metadata_column
WHEN OLD.name IS NOT NEW.name
    OR OLD.description IS NOT NEW.description
    OR OLD.data_type IS NOT NEW.data_type
    OR OLD.is_nullable IS NOT NEW.is_nullable
    OR OLD.default_value IS NOT NEW.default_value
    OR OLD.is_unique IS NOT NEW.is_unique
    OR OLD.ordinal_position IS NOT NEW.ordinal_position
    OR OLD.fk_table_id IS NOT NEW.fk_table_id
    OR OLD.fk_column_id IS NOT NEW.fk_column_id
    OR OLD.deleted_at IS NOT NEW.deleted_at
BEGIN
    INSERT INTO metadata_column_history (column_id, table_id, name, description, data_type, is_nullable, default_value, is_unique, ordinal_position, fk_table_id, fk_column_id, changed_at, changed_by)
    VALUES (OLD.id, OLD.table_id, OLD.name, OLD.description, OLD.data_type, OLD.is_nullable, OLD.default_value, OLD.is_unique, OLD.ordinal_position, OLD.fk_table_id, OLD.fk_column_id, strftime('%Y-%m-%dT%H:%M:%f+00:00', 'now'), OLD.updated_by);
END;

CREATE TRIGGER history_index BEFORE UPDATE ON metadata_index
WHEN OLD.name IS NOT NEW.name
    OR OLD.type IS NOT NEW.type
    OR OLD.definition IS NOT NEW.definition
    OR OLD.is_unique IS NOT NEW.is_unique
    OR OLD.is_primary IS NOT NEW.is_primary
    OR OLD.deleted_at IS NOT NEW.deleted_at
BEGIN
    INSERT INTO metadata_index_history (index_id, table_id, index_oid, name, type, definition, is_unique, is_primary, changed_at, changed_by)
    VALUES (OLD.id, OLD.table_id, OLD.oid, OLD.name, OLD.type, OLD.definition, OLD.is_unique, OLD.is_primary, strftime('%Y-%m-%dT%H:%M:%f+00:00', 'now'), OLD.updated_by);
END;
