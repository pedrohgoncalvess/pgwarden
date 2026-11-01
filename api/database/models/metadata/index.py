from sqlalchemy import (
    Column, BigInteger, Text, 
    Boolean, DateTime, func, ForeignKey
)
from sqlalchemy.dialects.postgresql import UUID
from database.models.base_model import Base


class Index(Base):
    __tablename__ = "index"
    __table_args__ = {"schema": "metadata"}

    id          = Column(BigInteger, primary_key=True, autoincrement=True)
    public_id   = Column(UUID(as_uuid=True), nullable=False, server_default=func.uuid_generate_v4(), unique=True)
    database_id = Column(BigInteger, ForeignKey("metadata.database.id", ondelete="CASCADE"), nullable=False)
    table_id    = Column(BigInteger, ForeignKey("metadata.table.id", ondelete="CASCADE"), nullable=False)
    oid         = Column(BigInteger, nullable=False)
    name        = Column(Text, nullable=False)
    type        = Column(Text, nullable=False)
    definition  = Column(Text, nullable=False)
    is_unique   = Column(Boolean, nullable=False, default=False)
    is_primary  = Column(Boolean, nullable=False, default=False)
    created_at  = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    created_by  = Column(BigInteger, nullable=True)
    updated_at  = Column(DateTime(timezone=True), nullable=True, onupdate=func.now())
    updated_by  = Column(BigInteger, nullable=True)
    deleted_at  = Column(DateTime(timezone=True), nullable=True)
    deleted_by  = Column(BigInteger, nullable=True)

    is_valid = Column(Boolean, nullable=True)
