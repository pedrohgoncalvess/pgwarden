from sqlalchemy import BigInteger, Column, DateTime, Float, ForeignKey, Index, Text, func
from sqlalchemy.dialects.postgresql import JSONB

from analytics.database.models.base_model import Base


class QueryAnalysisFinding(Base):
    __tablename__ = "query_analysis_finding"
    __table_args__ = (
        Index("query_analysis_finding_analysis_idx", "analysis_id"),
        Index("query_analysis_finding_type_idx", "type"),
        {"schema": "analytics"},
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    analysis_id = Column(BigInteger, ForeignKey("analytics.query_analysis.id", ondelete="CASCADE"), nullable=False)
    type = Column(Text, nullable=False)
    severity = Column(Text, nullable=False)
    confidence = Column(Float, nullable=False)
    title = Column(Text, nullable=False)
    explanation = Column(Text, nullable=False)
    recommendation = Column(Text, nullable=True)
    evidence = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
