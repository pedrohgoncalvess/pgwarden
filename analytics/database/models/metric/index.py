from sqlalchemy import BigInteger, Column, DateTime

from analytics.database.models.base_model import Base


class IndexMetric(Base):
    __tablename__ = "index"
    __table_args__ = {"schema": "metric"}

    collected_at = Column(DateTime(timezone=True), primary_key=True)
    index_id = Column(BigInteger, primary_key=True)
    size = Column(BigInteger, nullable=False)
    scan_qt = Column(BigInteger, nullable=True)
    tup_read_qt = Column(BigInteger, nullable=True)
    tup_fetch_qt = Column(BigInteger, nullable=True)
    blks_read = Column(BigInteger, nullable=True)
    blks_hit = Column(BigInteger, nullable=True)
