from sqlalchemy import BigInteger, Column, DateTime, Float

from analytics.database.models.base_model import Base


class RamMetric(Base):
    __tablename__ = "ram"
    __table_args__ = {"schema": "metric"}

    collected_at = Column(DateTime(timezone=True), primary_key=True)
    server_id = Column(BigInteger, primary_key=True)
    total_bytes = Column(BigInteger, nullable=True)
    used_bytes = Column(BigInteger, nullable=True)
    available_bytes = Column(BigInteger, nullable=True)
    percent = Column(Float, nullable=True)
