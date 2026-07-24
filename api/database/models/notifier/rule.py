from sqlalchemy import (
    Column, BigInteger, Text,
    Float, Boolean, DateTime, func
)

from database.models.base_model import Base


class NotifierRule(Base):
    __tablename__ = "rule"
    __table_args__ = {"schema": "notifier"}

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    name = Column(Text, nullable=False, unique=True)
    interval_seconds = Column(Float, nullable=False, default=60)
    cooldown_seconds = Column(Float, nullable=False, default=1800)
    window_minutes = Column(Float, nullable=False, default=5)
    enabled = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=True, onupdate=func.now())
