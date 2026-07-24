from sqlalchemy import (
    Column, BigInteger, Text,
    Boolean, DateTime, func
)

from database.models.base_model import Base


class NotifierChannel(Base):
    __tablename__ = "channel"
    __table_args__ = {"schema": "notifier"}

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    name = Column(Text, nullable=False, unique=True)
    enabled = Column(Boolean, nullable=False, default=False)
    credentials = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=True, onupdate=func.now())
