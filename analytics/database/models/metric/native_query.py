from sqlalchemy import BigInteger, Column, DateTime, Float, Integer, Text

from analytics.database.models.base_model import Base


class NativeQueryMetric(Base):
    __tablename__ = "native_query"
    __table_args__ = {"schema": "metric"}

    collected_at = Column(DateTime(timezone=True), primary_key=True)
    database_id = Column(BigInteger, primary_key=True)
    pid = Column(Integer, primary_key=True)
    backend_start = Column(DateTime(timezone=True), primary_key=True)
    query = Column(Text, nullable=True)
    query_hash = Column(Text, nullable=True)
    query_duration_ms = Column(Float, nullable=True)
