from sqlalchemy import BigInteger, Column, DateTime

from analytics.database.models.base_model import Base


class DatabaseStatMetric(Base):
    __tablename__ = "database_stat"
    __table_args__ = {"schema": "metric"}

    collected_at = Column(DateTime(timezone=True), primary_key=True)
    database_id = Column(BigInteger, primary_key=True)
    xact_commit = Column(BigInteger, nullable=True)
    xact_rollback = Column(BigInteger, nullable=True)
    blks_read = Column(BigInteger, nullable=True)
    blks_hit = Column(BigInteger, nullable=True)
    tup_returned = Column(BigInteger, nullable=True)
    tup_fetched = Column(BigInteger, nullable=True)
    tup_inserted = Column(BigInteger, nullable=True)
    tup_updated = Column(BigInteger, nullable=True)
    tup_deleted = Column(BigInteger, nullable=True)
    conflicts = Column(BigInteger, nullable=True)
    deadlocks = Column(BigInteger, nullable=True)
    db_size_bytes = Column(BigInteger, nullable=True)
