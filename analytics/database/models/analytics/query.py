from sqlalchemy import BigInteger, Boolean, Column, DateTime, Text, UniqueConstraint, func

from analytics.database.models.base_model import Base


class Query(Base):
    __tablename__ = "query"
    __table_args__ = (
        UniqueConstraint("database_id", "query", "pg_query_id", name="query_database_query_identity_key"),
        {"schema": "analytics"},
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    database_id = Column(BigInteger, nullable=False)
    query = Column(Text, nullable=False)
    user_name = Column(Text, nullable=True)
    application_name = Column(Text, nullable=True)
    hash = Column(Text, nullable=False)
    pg_query_id = Column(BigInteger, nullable=True)
    seen_activity = Column(Boolean, nullable=False, server_default="false")
    seen_statements = Column(Boolean, nullable=False, server_default="false")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
