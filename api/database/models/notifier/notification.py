from sqlalchemy import BigInteger, Boolean, Column, DateTime, Text, func
from sqlalchemy.dialects.postgresql import JSONB

from database.models.base_model import Base


class Notification(Base):
    """Persist an event shown in the frontend notification center."""

    __tablename__ = "notification"
    __table_args__ = {"schema": "notifier"}

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    message = Column(Text, nullable=False)
    hidden = Column(Boolean, nullable=False, default=False)
    params = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
