from sqlalchemy import (
    Column, BigInteger, Text,
    DateTime, func, ForeignKey
)
from database.models.base_model import Base


class IndexDoc(Base):
    __tablename__ = "index"
    __table_args__ = {"schema": "doc"}

    id             = Column(BigInteger, primary_key=True, autoincrement=True)
    index_id       = Column(BigInteger, ForeignKey("metadata.index.id", ondelete="CASCADE"), nullable=False, unique=True)
    description    = Column(Text, nullable=True)
    created_at     = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at     = Column(DateTime(timezone=True), nullable=True, onupdate=func.now())
    updated_by     = Column(BigInteger, nullable=True)
