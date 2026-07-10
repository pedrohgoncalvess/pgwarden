from sqlalchemy import BigInteger, Column, DateTime

from analytics.database.models.base_model import Base


class TableMetric(Base):
    __tablename__ = "table"
    __table_args__ = {"schema": "metric"}

    collected_at = Column(DateTime(timezone=True), primary_key=True)
    table_id = Column(BigInteger, primary_key=True)
    n_live_tup = Column(BigInteger, nullable=True)
    n_dead_tup = Column(BigInteger, nullable=True)
    table_size_bytes = Column(BigInteger, nullable=True)
    last_vacuum = Column(DateTime(timezone=True), nullable=True)
    last_autovacuum = Column(DateTime(timezone=True), nullable=True)
    last_analyze = Column(DateTime(timezone=True), nullable=True)
    last_autoanalyze = Column(DateTime(timezone=True), nullable=True)
    seq_scan = Column(BigInteger, nullable=True)
    idx_scan = Column(BigInteger, nullable=True)
    heap_blks_read = Column(BigInteger, nullable=True)
    heap_blks_hit = Column(BigInteger, nullable=True)
    modifications_since_last_analyze = Column(BigInteger, nullable=True)
