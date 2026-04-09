from sqlalchemy import (
    Column, BigInteger, Text, 
    Boolean, DateTime, func, ForeignKey
)
from sqlalchemy.dialects.postgresql import UUID

from database.models.base_model import Base


class Database(Base):
    __tablename__ = "database"
    __table_args__ = {"schema": "metadata"}

    id           = Column(BigInteger, primary_key=True, autoincrement=True)
    oid          = Column(BigInteger, nullable=True) # OID is usually 4 bytes, BigInteger is safe
    public_id    = Column(UUID(as_uuid=True), nullable=False, server_default=func.uuid_generate_v4(), unique=True)
    server_id    = Column(BigInteger, ForeignKey("collector.server.id", ondelete="CASCADE"), nullable=False)
    db_name      = Column(Text, nullable=False)
    is_active    = Column(Boolean, nullable=False, default=True)
    last_seen_at = Column(DateTime(timezone=True), nullable=True)
    last_error   = Column(Text, nullable=True)
    created_at   = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at   = Column(DateTime(timezone=True), nullable=True, onupdate=func.now())
    deleted_at   = Column(DateTime(timezone=True), nullable=True)
