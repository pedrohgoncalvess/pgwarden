"""Typed snapshots referencing deduplicated statement text."""

from sqlalchemy import BigInteger, Boolean, Column, DateTime, Float, ForeignKey, Integer, Numeric, Text, UniqueConstraint, select
from sqlalchemy.orm import column_property
from analytics.database.models.base_model import Base


class StatementText(Base):
    """Store SQL text once per monitored database and content fingerprint."""

    __tablename__ = "statement_text"
    __table_args__ = (UniqueConstraint("database_id", "fingerprint"), {"schema": "metric"})
    id = Column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    database_id = Column(BigInteger, ForeignKey("metadata.database.id", ondelete="CASCADE"), nullable=False)
    fingerprint = Column(Text, nullable=False)
    query = Column(Text, nullable=False)
    query_hash = Column(Text)


class QueryWorkloadMetric(Base):
    """Retain structured counters and an optional reference to visible SQL."""

    __tablename__ = "query_workload"
    __table_args__ = {"schema": "metric"}
    collected_at = Column(DateTime(timezone=True), primary_key=True)
    database_id = Column(BigInteger, ForeignKey("metadata.database.id", ondelete="CASCADE"), primary_key=True)
    query_id = Column(BigInteger, primary_key=True)
    user_id = Column(BigInteger, primary_key=True)
    is_toplevel = Column(Boolean, primary_key=True)
    calls = Column(BigInteger, nullable=False)
    total_exec_time = Column(Float, nullable=False)
    shared_blks_read = Column(BigInteger, nullable=False)
    shared_blks_hit = Column(BigInteger, nullable=False)
    stats_reset = Column(DateTime(timezone=True))
    dealloc = Column(BigInteger, nullable=False)
    user_name = Column(Text)
    statement_text_id = Column(BigInteger, ForeignKey("metric.statement_text.id"))
    plans = Column(BigInteger)
    rows = Column(BigInteger)
    shared_blks_dirtied = Column(BigInteger)
    shared_blks_written = Column(BigInteger)
    local_blks_hit = Column(BigInteger)
    local_blks_read = Column(BigInteger)
    local_blks_dirtied = Column(BigInteger)
    local_blks_written = Column(BigInteger)
    temp_blks_read = Column(BigInteger)
    temp_blks_written = Column(BigInteger)
    wal_records = Column(BigInteger)
    wal_fpi = Column(BigInteger)
    wal_buffers_full = Column(BigInteger)
    jit_functions = Column(BigInteger)
    jit_inlining_count = Column(BigInteger)
    jit_optimization_count = Column(BigInteger)
    jit_emission_count = Column(BigInteger)
    jit_deform_count = Column(BigInteger)
    parallel_workers_to_launch = Column(BigInteger)
    parallel_workers_launched = Column(BigInteger)
    total_plan_time = Column(Float)
    min_plan_time = Column(Float)
    max_plan_time = Column(Float)
    mean_plan_time = Column(Float)
    stddev_plan_time = Column(Float)
    min_exec_time = Column(Float)
    max_exec_time = Column(Float)
    mean_exec_time = Column(Float)
    stddev_exec_time = Column(Float)
    blk_read_time = Column(Float)
    blk_write_time = Column(Float)
    shared_blk_read_time = Column(Float)
    shared_blk_write_time = Column(Float)
    local_blk_read_time = Column(Float)
    local_blk_write_time = Column(Float)
    temp_blk_read_time = Column(Float)
    temp_blk_write_time = Column(Float)
    jit_generation_time = Column(Float)
    jit_inlining_time = Column(Float)
    jit_optimization_time = Column(Float)
    jit_emission_time = Column(Float)
    jit_deform_time = Column(Float)
    stats_since = Column(DateTime(timezone=True))
    minmax_stats_since = Column(DateTime(timezone=True))
    wal_bytes = Column(Numeric(30, 0))
    source_database_oid = Column(BigInteger)
    query = column_property(
        select(StatementText.query).where(StatementText.id == statement_text_id)
        .correlate_except(StatementText).scalar_subquery()
    )
    query_hash = column_property(
        select(StatementText.query_hash).where(StatementText.id == statement_text_id)
        .correlate_except(StatementText).scalar_subquery()
    )
