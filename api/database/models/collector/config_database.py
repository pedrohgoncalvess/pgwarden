from sqlalchemy import (
    Column, BigInteger, Text,
    Float, Integer, Boolean, DateTime, ForeignKey, func
)
from database.models.base_model import Base


class ConfigDatabase(Base):
    __tablename__ = "config_database"
    __table_args__ = {"schema": "collector"}

    id          = Column(BigInteger, primary_key=True, autoincrement=True)
    database_id = Column(BigInteger, ForeignKey("metadata.database.id", ondelete="CASCADE"), nullable=False)
    name        = Column(Text, nullable=False)
    interval    = Column(Float, nullable=False)
    is_paused   = Column(Boolean, nullable=False, default=False)
    next_run_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
