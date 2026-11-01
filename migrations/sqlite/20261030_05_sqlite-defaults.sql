-- depends: 20261030_04_sqlite-collector

CREATE TRIGGER default_config_database AFTER INSERT ON metadata_database
BEGIN
    INSERT INTO collector_config_database (database_id, name, interval) VALUES
        (NEW.id, 'table_collector', 1800),
        (NEW.id, 'column_collector', 1800),
        (NEW.id, 'index_collector', 1800),
        (NEW.id, 'table_metric_collector', 1800),
        (NEW.id, 'column_metric_collector', 1800),
        (NEW.id, 'index_metric_collector', 1800),
        (NEW.id, 'database_stat_collector', 3),
        (NEW.id, 'lock_metric_collector', 3),
        (NEW.id, 'session_metric_collector', 3),
        (NEW.id, 'native_query_collector', 0.5);
END;

CREATE TRIGGER default_config_server AFTER INSERT ON collector_server
BEGIN
    INSERT INTO collector_config_server (server_id, name, interval) VALUES
        (NEW.id, 'cpu_collector', 20),
        (NEW.id, 'ram_collector', 20),
        (NEW.id, 'io_collector', 5),
        (NEW.id, 'disk_collector', 1800);
END;

CREATE INDEX command_pending ON collector_command (created_at) WHERE executed_at IS NULL;

CREATE INDEX config_database_target ON collector_config_database (database_id);

CREATE INDEX config_server_target ON collector_config_server (server_id);
