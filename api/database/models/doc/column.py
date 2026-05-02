from sqlalchemy import (
    Column, BigInteger, Text,
    Boolean, DateTime, func, ForeignKey
)
from database.models.base_model import Base


class ColumnDoc(Base):
    __tablename__ = "column"
    __table_args__ = {"schema": "doc"}

    id             = Column(BigInteger, primary_key=True, autoincrement=True)
    column_id      = Column(BigInteger, ForeignKey("metadata.column.id", ondelete="CASCADE"), nullable=False, unique=True)
    description    = Column(Text, nullable=True)
    is_pii         = Column(Boolean, nullable=False, default=False)
    sample_values  = Column(Text, nullable=True)
    created_at     = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at     = Column(DateTime(timezone=True), nullable=True, onupdate=func.now())
    updated_by     = Column(BigInteger, nullable=True)
