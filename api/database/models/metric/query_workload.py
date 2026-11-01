from sqlalchemy import BigInteger, Boolean, Column, DateTime, Float, ForeignKey
from database.models.base_model import Base


class QueryWorkloadMetric(Base):
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
    stats_reset = Column(DateTime(timezone=True), nullable=True)
    dealloc = Column(BigInteger, nullable=False)
