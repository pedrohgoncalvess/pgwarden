from sqlalchemy import BigInteger, Column, DateTime, Float, ForeignKey, Index, Text, func

from analytics.database.models.base_model import Base


class QueryAnalysis(Base):
    __tablename__ = "query_analysis"
    __table_args__ = (
        Index("query_analysis_query_idx", "query_id"),
        Index("query_analysis_run_idx", "run_id"),
        {"schema": "analytics"},
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    run_id = Column(BigInteger, ForeignKey("analytics.run.id", ondelete="CASCADE"), nullable=False)
    query_id = Column(BigInteger, ForeignKey("analytics.query.id", ondelete="CASCADE"), nullable=False)
    database_id = Column(BigInteger, ForeignKey("metadata.database.id", ondelete="CASCADE"), nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=True)
    ended_at = Column(DateTime(timezone=True), nullable=True)
    duration_ms = Column(Float, nullable=True)
    overall_score = Column(Float, nullable=False, default=0.0)
    summary = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
