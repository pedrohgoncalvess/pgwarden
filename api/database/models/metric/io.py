from sqlalchemy import Column, BigInteger, DateTime, ForeignKey
from database.models.base_model import Base


class IoMetric(Base):
    __tablename__ = "io"
    __table_args__ = {"schema": "metric"}

    collected_at = Column(DateTime(timezone=True), primary_key=True)
    server_id    = Column(BigInteger, ForeignKey("collector.server.id", ondelete="CASCADE"), primary_key=True)
    read_bytes   = Column(BigInteger, nullable=True)
    write_bytes  = Column(BigInteger, nullable=True)
    read_count   = Column(BigInteger, nullable=True)
    write_count  = Column(BigInteger, nullable=True)
