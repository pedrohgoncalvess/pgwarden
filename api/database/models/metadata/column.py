from sqlalchemy import (
    Column, BigInteger, Text, 
    Boolean, Integer, DateTime, func, ForeignKey
)
from sqlalchemy.dialects.postgresql import UUID
from database.models.base_model import Base


class ColumnModel(Base):
    __tablename__ = "column"
    __table_args__ = {"schema": "metadata"}

    id               = Column(BigInteger, primary_key=True, autoincrement=True)
    public_id        = Column(UUID(as_uuid=True), nullable=False, server_default=func.uuid_generate_v4(), unique=True)
    table_id         = Column(BigInteger, ForeignKey("metadata.table.id", ondelete="CASCADE"), nullable=False)
    name             = Column(Text, nullable=False)
    description      = Column(Text, nullable=True)
    data_type        = Column(Text, nullable=False)
    is_nullable      = Column(Boolean, nullable=False, default=True)
    default_value    = Column(Text, nullable=True)
    is_unique        = Column(Boolean, nullable=False, default=False)
    ordinal_position = Column(Integer, nullable=False)
    fk_table_id      = Column(BigInteger, ForeignKey("metadata.table.id", ondelete="SET NULL"), nullable=True)
    fk_column_id     = Column(BigInteger, ForeignKey("metadata.column.id", ondelete="SET NULL"), nullable=True)
    created_at       = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    created_by       = Column(BigInteger, nullable=True)
    updated_at       = Column(DateTime(timezone=True), nullable=True, onupdate=func.now())
    updated_by       = Column(BigInteger, nullable=True)
    deleted_at       = Column(DateTime(timezone=True), nullable=True)
    deleted_by       = Column(BigInteger, nullable=True)
