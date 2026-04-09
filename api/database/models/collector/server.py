from sqlalchemy import (
    Column, BigInteger, Text, 
    DateTime, func, ARRAY, String
)
from sqlalchemy.dialects.postgresql import UUID
from database.models.base_model import Base


class Server(Base):
    __tablename__ = "server"
    __table_args__ = {"schema": "collector"}

    id              = Column(BigInteger, primary_key=True, autoincrement=True)
    public_id       = Column(UUID(as_uuid=True), nullable=False, server_default=func.uuid_generate_v4(), unique=True)
    name            = Column(Text, nullable=False)
    host            = Column(Text, nullable=False)
    port            = Column(Text, nullable=False)
    username        = Column(Text, nullable=False)
    password        = Column(Text, nullable=False)
    ssl_mode        = Column(Text, nullable=False, server_default='prefer')
    last_seen_at    = Column(DateTime(timezone=True), nullable=True)
    last_error      = Column(Text, nullable=True)
    ignore_patterns = Column(ARRAY(Text), nullable=True)
    ignore_tables   = Column(ARRAY(Text), nullable=True)
    include_tables  = Column(ARRAY(Text), nullable=True)
    created_at      = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at      = Column(DateTime(timezone=True), nullable=True, onupdate=func.now())
    deleted_at      = Column(DateTime(timezone=True), nullable=True)
