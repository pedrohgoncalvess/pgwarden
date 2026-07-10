from sqlalchemy import BigInteger, Column, DateTime, Text, func

from analytics.database.models.base_model import Base


class Query(Base):
    __tablename__ = "query"
    __table_args__ = {"schema": "analytics"}

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    database_id = Column(BigInteger, nullable=False)
    query = Column(Text, nullable=False, unique=True)
    user_name = Column(Text, nullable=True)
    application_name = Column(Text, nullable=True)
    hash = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
