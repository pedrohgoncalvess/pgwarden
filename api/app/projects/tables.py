"""SQLAlchemy Core definitions for ingestion administration."""

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Integer,
    MetaData,
    String,
    Table,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID


metadata = MetaData(schema="ingestion")
project = Table(
    "project",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("name", String(100), nullable=False),
    Column("enabled", Boolean, nullable=False),
    Column("key_expiration_days", Integer),
    Column("rotation_interval_days", Integer),
    Column("rotation_grace_hours", Integer, nullable=False),
    Column("next_rotation_at", DateTime(timezone=True)),
    Column("created_at", DateTime(timezone=True)),
    Column("last_event_at", DateTime(timezone=True)),
)
api_key = Table(
    "api_key",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("project_id", UUID(as_uuid=True), nullable=False),
    Column("key_hash", String(64), nullable=False),
    Column("prefix", String(16), nullable=False),
    Column("encrypted_secret", Text),
    Column("created_at", DateTime(timezone=True)),
    Column("expires_at", DateTime(timezone=True)),
    Column("retire_at", DateTime(timezone=True)),
    Column("revoked_at", DateTime(timezone=True)),
    Column("last_used_at", DateTime(timezone=True)),
)
event = Table(
    "event",
    metadata,
    Column("project_id", UUID(as_uuid=True), primary_key=True),
    Column("source_id", UUID(as_uuid=True), primary_key=True),
    Column("event_id", UUID(as_uuid=True), primary_key=True),
    Column("table_name", Text),
    Column("fingerprint", String(64)),
    Column("payload", JSONB),
    Column("received_at", DateTime(timezone=True)),
)
entity = Table(
    "entity",
    metadata,
    Column("project_id", UUID(as_uuid=True), primary_key=True),
    Column("source_id", UUID(as_uuid=True), primary_key=True),
    Column("table_name", Text, primary_key=True),
    Column("local_id", BigInteger, primary_key=True),
    Column("central_id", BigInteger),
    Column("observed_at", DateTime(timezone=True)),
)
