from sqlalchemy import BigInteger, Column, DateTime, Float, Integer

from analytics.database.models.base_model import Base


class CpuMetric(Base):
    __tablename__ = "cpu"
    __table_args__ = {"schema": "metric"}

    collected_at = Column(DateTime(timezone=True), primary_key=True)
    server_id = Column(BigInteger, primary_key=True)
    cpu_percent = Column(Float, nullable=True)
    cpu_count = Column(Integer, nullable=True)
