from sqlalchemy import BigInteger, Boolean, Column, DateTime, ForeignKey, Index, Integer, Text, func

from analytics.database.models.base_model import Base


class QueryTableHit(Base):
    __tablename__ = "query_table_hit"
    __table_args__ = (
        Index("query_table_hit_query_idx", "query_id"),
        {"schema": "analytics"},
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    query_id = Column(Integer, ForeignKey("analytics.query.id", ondelete="CASCADE"), nullable=False)
    schema_name = Column(Text, nullable=False)
    table_name = Column(Text, nullable=False)
    alias = Column(Text, nullable=True)
    is_foreign = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
