"""Storage statements used by the collector execution loops."""

from database import load_storage_query


GET_DB_CONFIG = load_storage_query(
    schema="collector", table="config_database", query_type="SELECT", query_name="by_id"
)
GET_DB_CONFIGS_BY_DB = load_storage_query(
    schema="collector",
    table="config_database",
    query_type="SELECT",
    query_name="by_database_id",
)
SET_DB_RUNNING = load_storage_query(
    schema="collector",
    table="config_database",
    query_type="UPDATE",
    query_name="running",
)
SET_DB_SUCCESS = load_storage_query(
    schema="collector",
    table="config_database",
    query_type="UPDATE",
    query_name="success",
)
SET_DB_ERROR = load_storage_query(
    schema="collector", table="config_database", query_type="UPDATE", query_name="error"
)
SET_DB_FORCE = load_storage_query(
    schema="collector",
    table="config_database",
    query_type="UPDATE",
    query_name="set_next_run_on_force",
)

GET_SRV_CONFIG = load_storage_query(
    schema="collector", table="config_server", query_type="SELECT", query_name="by_id"
)
GET_SRV_CONFIGS_BY_SRV = load_storage_query(
    schema="collector",
    table="config_server",
    query_type="SELECT",
    query_name="by_server_id",
)
SET_SRV_RUNNING = load_storage_query(
    schema="collector", table="config_server", query_type="UPDATE", query_name="running"
)
SET_SRV_SUCCESS = load_storage_query(
    schema="collector", table="config_server", query_type="UPDATE", query_name="success"
)
SET_SRV_ERROR = load_storage_query(
    schema="collector", table="config_server", query_type="UPDATE", query_name="error"
)
SET_SRV_FORCE = load_storage_query(
    schema="collector",
    table="config_server",
    query_type="UPDATE",
    query_name="set_next_run_on_force",
)

CONSUME_COMMAND = load_storage_query(
    schema="collector",
    table="command",
    query_type="UPDATE",
    query_name="consume_command",
)
INSERT_RUN_SUCCESS_DB = load_storage_query(
    schema="collector", table="run", query_type="INSERT", query_name="success_database"
)
INSERT_RUN_ERROR_DB = load_storage_query(
    schema="collector", table="run", query_type="INSERT", query_name="error_database"
)
INSERT_RUN_SUCCESS_SRV = load_storage_query(
    schema="collector", table="run", query_type="INSERT", query_name="success_server"
)
INSERT_RUN_ERROR_SRV = load_storage_query(
    schema="collector", table="run", query_type="INSERT", query_name="error_server"
)

UPDATE_LAST_SEEN_DB = load_storage_query(
    schema="metadata", table="database", query_type="UPDATE", query_name="last_seen"
)
UPDATE_LAST_SEEN_SRV = load_storage_query(
    schema="collector", table="server", query_type="UPDATE", query_name="last_seen"
)
