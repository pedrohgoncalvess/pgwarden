"""Versioned envelopes for SQLite row snapshots sent by the HTTP sender."""

from typing import Any, Literal, Self
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator


EntityTable = Literal[
    "collector_server",
    "metadata_database",
    "metadata_table",
    "metadata_column",
    "metadata_index",
    "metadata_index_column",
]
MetricTable = Literal[
    "metric_cpu",
    "metric_ram",
    "metric_disk",
    "metric_io",
    "metric_database_stat",
    "metric_table",
    "metric_column",
    "metric_index",
    "metric_session",
    "metric_lock",
    "metric_native_query",
    "metric_query_workload",
]


class CollectionEvent(BaseModel):
    """One immutable delivery identifier and a row using local SQLite IDs."""

    model_config = ConfigDict(extra="forbid")
    event_id: UUID
    occurred_at: AwareDatetime
    table: EntityTable | MetricTable | Literal["base_service_heartbeat"]
    local_id: int | None = Field(default=None, gt=0, le=9223372036854775807)
    operation: Literal["upsert", "delete"] = "upsert"
    data: dict[str, Any]

    @model_validator(mode="after")
    def validate_identity(self) -> Self:
        """Require local IDs for entities and constrain physical deletion."""
        if (
            not self.table.startswith("metric_")
            and self.table not in ("metadata_index_column", "base_service_heartbeat")
            and self.local_id is None
        ):
            raise ValueError("Entity events require local_id")
        if self.operation == "delete" and self.table != "metadata_index_column":
            raise ValueError(
                "Only index-column relationships support physical deletion"
            )
        return self


class EventBatch(BaseModel):
    """A bounded, retryable batch from one persistent collector installation."""

    model_config = ConfigDict(extra="forbid")
    version: Literal[1] = 1
    source_id: UUID
    events: list[CollectionEvent] = Field(min_length=1, max_length=500)


class IngestionResult(BaseModel):
    """Acknowledge only committed events and optionally hand off a successor key."""

    project_id: UUID
    accepted: int
    duplicates: int
    acknowledged_event_ids: list[UUID]
    replacement_key: str | None = None


def get_batch_schema() -> dict:
    """Inline nested definitions so the streamed body has valid OpenAPI refs."""
    schema = EventBatch.model_json_schema()
    definitions = schema.pop("$defs", {})

    def expand(value: Any) -> Any:
        if isinstance(value, dict):
            if "$ref" in value:
                return expand(definitions[value["$ref"].rsplit("/", 1)[-1]])
            return {key: expand(item) for key, item in value.items()}
        if isinstance(value, list):
            return [expand(item) for item in value]
        return value

    return expand(schema)
