from sqlalchemy import (
    Column, BigInteger, Text,
    DateTime, func, ForeignKey, UniqueConstraint
)
from database.models.base_model import Base


class SchemaDoc(Base):
    __tablename__ = "schema"
    __table_args__ = (
        UniqueConstraint("database_id", "schema_name"),
        {"schema": "doc"}
    )

    id             = Column(BigInteger, primary_key=True, autoincrement=True)
    database_id    = Column(BigInteger, ForeignKey("metadata.database.id", ondelete="CASCADE"), nullable=False)
    schema_name    = Column(Text, nullable=False)
    description    = Column(Text, nullable=True)
    owner          = Column(Text, nullable=True)
    classification = Column(Text, default="internal")
    created_at     = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at     = Column(DateTime(timezone=True), nullable=True, onupdate=func.now())
    updated_by     = Column(BigInteger, nullable=True)
