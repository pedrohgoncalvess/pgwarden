from sqlalchemy import Column, BigInteger, Integer, Float, DateTime, ForeignKey
from database.models.base_model import Base


class CpuMetric(Base):
    __tablename__ = "cpu"
    __table_args__ = {"schema": "metric"}

    collected_at = Column(DateTime(timezone=True), primary_key=True)
    server_id    = Column(BigInteger, ForeignKey("collector.server.id", ondelete="CASCADE"), primary_key=True)
    cpu_percent  = Column(Float, nullable=True)
    cpu_count    = Column(Integer, nullable=True)
