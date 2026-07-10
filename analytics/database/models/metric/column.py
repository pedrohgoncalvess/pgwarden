from sqlalchemy import BigInteger, Column, DateTime, Float, Integer

from analytics.database.models.base_model import Base


class ColumnMetric(Base):
    __tablename__ = "column"
    __table_args__ = {"schema": "metric"}

    collected_at = Column(DateTime(timezone=True), primary_key=True)
    column_id = Column(BigInteger, primary_key=True)
    avg_width = Column(Integer, nullable=True)
    null_fraction = Column(Float, nullable=True)
    n_distinct = Column(Float, nullable=True)
    estimated_size = Column(BigInteger, nullable=True)
