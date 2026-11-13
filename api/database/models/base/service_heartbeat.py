"""Shared service liveness reported by local or remote collectors."""

from sqlalchemy import Column, DateTime, Text

from database.models.base_model import Base


class ServiceHeartbeat(Base):
    __tablename__ = "service_heartbeat"
    __table_args__ = {"schema": "base"}

    service = Column(Text, primary_key=True)
    updated_at = Column(DateTime(timezone=True), nullable=False)
