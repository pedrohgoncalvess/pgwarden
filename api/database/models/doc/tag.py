from sqlalchemy import (
    Column, BigInteger, Text,
    DateTime, func
)
from sqlalchemy.dialects.postgresql import UUID
from database.models.base_model import Base


class Tag(Base):
    __tablename__ = "tag"
    __table_args__ = {"schema": "doc"}

    id          = Column(BigInteger, primary_key=True, autoincrement=True)
    public_id   = Column(UUID(as_uuid=True), nullable=False, server_default=func.uuid_generate_v4(), unique=True)
    name        = Column(Text, nullable=False)
    description = Column(Text, nullable=True)
    color       = Column(Text, default="#6366F1")
    type        = Column(Text, nullable=False, default="default")
    created_at  = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
