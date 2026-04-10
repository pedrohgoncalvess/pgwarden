from sqlalchemy import Column, BigInteger, Float, Text, DateTime, ForeignKey
from database.models.base_model import Base


class DiskMetric(Base):
    __tablename__ = "disk"
    __table_args__ = {"schema": "metric"}

    collected_at = Column(DateTime(timezone=True), primary_key=True)
    server_id    = Column(BigInteger, ForeignKey("collector.server.id", ondelete="CASCADE"), primary_key=True)
    mount_point  = Column(Text, primary_key=True)
    total_bytes  = Column(BigInteger, nullable=True)
    used_bytes   = Column(BigInteger, nullable=True)
    free_bytes   = Column(BigInteger, nullable=True)
    percent      = Column(Float, nullable=True)
