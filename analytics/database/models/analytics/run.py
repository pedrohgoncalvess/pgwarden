from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Index, Text, func

from analytics.database.models.base_model import Base


class AnalyticsRun(Base):
    __tablename__ = "run"
    __table_args__ = (
        Index("run_database_created_idx", "database_id", "created_at"),
        {"schema": "analytics"},
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    database_id = Column(BigInteger, ForeignKey("metadata.database.id", ondelete="CASCADE"), nullable=False)
    run_at = Column(DateTime(timezone=True), nullable=False)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
