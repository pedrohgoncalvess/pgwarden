from sqlalchemy import BigInteger, Boolean, CheckConstraint, Column, DateTime, ForeignKey, Integer, UniqueConstraint, func

from analytics.database.models.base_model import Base


class AnalyticsConfig(Base):
    __tablename__ = "config"
    __table_args__ = (
        UniqueConstraint("database_id", name="config_database_key"),
        CheckConstraint("run_interval >= 10", name="config_run_interval_min"),
        {"schema": "analytics"},
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    database_id = Column(BigInteger, ForeignKey("metadata.database.id", ondelete="CASCADE"), nullable=False)
    run_interval = Column(Integer, nullable=False, default=1800)
    last_seen = Column(DateTime(timezone=True), nullable=True)
    query_analytics_enabled = Column(Boolean, nullable=False, default=True)
    recommendation_enabled = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
