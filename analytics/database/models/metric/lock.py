from sqlalchemy import BigInteger, Boolean, Column, DateTime, Integer, Text

from analytics.database.models.base_model import Base


class LockMetric(Base):
    __tablename__ = "lock"
    __table_args__ = {"schema": "metric"}

    collected_at = Column(DateTime(timezone=True), primary_key=True)
    database_id = Column(BigInteger, primary_key=True)
    table_id = Column(BigInteger, primary_key=True)
    holder_pid = Column(Integer, primary_key=True)
    type = Column(Text, primary_key=True)
    mode = Column(Text, primary_key=True)
    is_granted = Column(Boolean, nullable=True)
    query_preview = Column(Text, nullable=True)
