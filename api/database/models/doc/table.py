from sqlalchemy import (
    Column, BigInteger, Text,
    DateTime, func, ForeignKey
)
from database.models.base_model import Base


class TableDoc(Base):
    __tablename__ = "table"
    __table_args__ = {"schema": "doc"}

    id             = Column(BigInteger, primary_key=True, autoincrement=True)
    table_id       = Column(BigInteger, ForeignKey("metadata.table.id", ondelete="CASCADE"), nullable=False, unique=True)
    description    = Column(Text, nullable=True)
    owner          = Column(Text, nullable=True)
    classification = Column(Text, default="internal")
    created_at     = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at     = Column(DateTime(timezone=True), nullable=True, onupdate=func.now())
    updated_by     = Column(BigInteger, nullable=True)
