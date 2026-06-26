from sqlalchemy import (
    Column, BigInteger, Integer, Text,
    DateTime, func, ForeignKey, ARRAY
)
from database.models.base_model import Base


class Run(Base):
    __tablename__ = "run"
    __table_args__ = {"schema": "collector"}

    id                = Column(BigInteger, primary_key=True, autoincrement=True)
    config_database_id = Column(Integer, ForeignKey("collector.config_database.id", ondelete="CASCADE"), nullable=True)
    config_server_id  = Column(Integer, ForeignKey("collector.config_server.id", ondelete="CASCADE"), nullable=True)
    command_id        = Column(BigInteger, ForeignKey("collector.command.id", ondelete="SET NULL"), nullable=True)
    status            = Column(Text, nullable=False)
    errors            = Column(ARRAY(Text), nullable=True)
    inserted_at       = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    finished_at       = Column(DateTime(timezone=True), nullable=True)
