from sqlalchemy import BigInteger, Column, DateTime, Text, func
from pgvector.sqlalchemy import Vector

from database.models.base_model import Base


class EmbeddingCache(Base):
    __tablename__ = "embedding_cache"
    __table_args__ = {"schema": "base"}

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    term = Column(Text, nullable=False, unique=True)
    embedding = Column(Vector(1024), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
