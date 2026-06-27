from sqlalchemy import (
    Column, BigInteger, Text,
    Boolean, DateTime, func, ForeignKey
)
from database.models.base_model import Base


class IndexHistory(Base):
    __tablename__ = "index_history"
    __table_args__ = {"schema": "metadata"}

    id          = Column(BigInteger, primary_key=True, autoincrement=True)
    index_id    = Column(BigInteger, ForeignKey("metadata.index.id", ondelete="CASCADE"), nullable=False)
    table_id    = Column(BigInteger, ForeignKey("metadata.table.id", ondelete="CASCADE"), nullable=False)
    index_oid   = Column(BigInteger, nullable=False)
    name        = Column(Text, nullable=False)
    type        = Column(Text, nullable=False)
    definition  = Column(Text, nullable=False)
    is_unique   = Column(Boolean, nullable=False)
    is_primary  = Column(Boolean, nullable=False)
    changed_at  = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    changed_by  = Column(BigInteger, nullable=True)
