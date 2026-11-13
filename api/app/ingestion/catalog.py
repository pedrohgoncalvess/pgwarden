"""Allowlisted destination tables and per-table row validation."""

from functools import lru_cache
import json
from ipaddress import ip_address
from decimal import Decimal
from typing import Annotated, Any, Literal

from fastapi import HTTPException
from pydantic import (
    AwareDatetime,
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    create_model,
)
from sqlalchemy import BigInteger, Boolean, DateTime, Float, Integer, Numeric
from sqlalchemy.dialects.postgresql import OID

from database.models.collector.server import Server
from database.models.base.service_heartbeat import ServiceHeartbeat
from database.models.metadata import (
    Database,
    Table as MetadataTable,
    ColumnModel,
    Index,
    IndexColumn,
)
from app.ingestion.statements import expand_legacy_statement
from database.models.metric import (
    CpuMetric,
    RamMetric,
    DiskMetric,
    IoMetric,
    DatabaseStat,
    TableMetric,
    ColumnMetric,
    IndexMetric,
    SessionMetric,
    LockMetric,
    NativeQueryMetric,
    QueryWorkloadMetric,
)


TABLES = {
    f"{model.__table__.schema}_{model.__tablename__}": model.__table__
    for model in (
        Server,
        Database,
        MetadataTable,
        ColumnModel,
        Index,
        IndexColumn,
        CpuMetric,
        RamMetric,
        DiskMetric,
        IoMetric,
        DatabaseStat,
        TableMetric,
        ColumnMetric,
        IndexMetric,
        SessionMetric,
        LockMetric,
        NativeQueryMetric,
        QueryWorkloadMetric,
        ServiceHeartbeat,
    )
}
REFERENCES = {
    "server_id": "collector_server",
    "database_id": "metadata_database",
    "table_id": "metadata_table",
    "column_id": "metadata_column",
    "index_id": "metadata_index",
    "fk_table_id": "metadata_table",
    "fk_column_id": "metadata_column",
}
EXCLUDED = {
    "id",
    "public_id",
    "created_by",
    "updated_by",
    "deleted_by",
    "ingestion_project_id",
    "statement_text_id",
}
SERVER_FIELDS = {
    "name",
    "last_seen_at",
    "last_error",
    "created_at",
    "updated_at",
    "deleted_at",
}


def validate_address(value: str) -> str:
    """Accept only an IPv4 or IPv6 address for client address columns."""
    return str(ip_address(value))


def validate_statement_data(value: str) -> str:
    try:
        if isinstance(json.loads(value), dict):
            return value
    except ValueError:
        pass
    raise ValueError("Statement statistics must be a JSON object")


@lru_cache(maxsize=32)
def get_row_model(name: str) -> type[BaseModel]:
    """Build a strict input model from the destination's allowlisted columns."""
    fields = {}
    for column in TABLES[name].columns:
        if (
            column.name in EXCLUDED
            or name == "collector_server"
            and column.name not in SERVER_FIELDS
        ):
            continue
        if name == "base_service_heartbeat" and column.name == "service":
            annotation = Literal["collector"]
        elif isinstance(column.type, DateTime):
            annotation = AwareDatetime
        elif isinstance(column.type, Boolean):
            annotation = bool
        elif isinstance(column.type, OID):
            annotation = Annotated[int, Field(ge=0, le=4294967295, strict=True)]
        elif isinstance(column.type, BigInteger) or column.name in REFERENCES:
            annotation = Annotated[
                int, Field(ge=-9223372036854775808, le=9223372036854775807, strict=True)
            ]
        elif isinstance(column.type, Integer):
            annotation = Annotated[
                int, Field(ge=-2147483648, le=2147483647, strict=True)
            ]
        elif isinstance(column.type, Float):
            annotation = Annotated[float, Field(allow_inf_nan=False)]
        elif isinstance(column.type, Numeric):
            annotation = Annotated[Decimal, Field(ge=0, max_digits=30, decimal_places=0, allow_inf_nan=False)]
        elif column.name == "client_addr":
            annotation = Annotated[str, AfterValidator(validate_address)]
        elif column.name == "statement_data":
            annotation = Annotated[str, Field(max_length=262144), AfterValidator(validate_statement_data)]
        else:
            annotation = Annotated[str, Field(max_length=262144)]
        optional = (
            column.nullable
            or column.server_default is not None
            or column.default is not None
        )
        fields[column.name] = (
            annotation | None if column.nullable else annotation,
            None if optional else ...,
        )
    if name == "metric_query_workload":
        fields.update(query=(Annotated[str, Field(max_length=262144)] | None, None),
                      query_hash=(Annotated[str, Field(max_length=64)] | None, None))
    return create_model(
        f"Ingest_{name}", __config__=ConfigDict(extra="forbid"), **fields
    )


def validate_row(name: str, data: dict[str, Any]) -> dict:
    """Reject unknown fields and malformed data before writing any event."""
    try:
        if name == "metric_query_workload":
            data = expand_legacy_statement(data)
        return get_row_model(name).model_validate(data).model_dump(exclude_unset=True)
    except (ValueError, TypeError) as error:
        if not isinstance(error, ValidationError):
            raise HTTPException(422, "Invalid statement statistics") from None
        fields = ", ".join(".".join(map(str, issue["loc"])) for issue in error.errors())
        raise HTTPException(422, f"Invalid {name} fields: {fields}") from None
