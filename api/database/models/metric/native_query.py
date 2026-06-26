from sqlalchemy import (
    Column, BigInteger, Integer, Float,
    DateTime, Text, ForeignKey
)
from sqlalchemy.dialects.postgresql import INET, OID
from database.models.base_model import Base


class NativeQueryMetric(Base):
    __tablename__ = "native_query"
    __table_args__ = {"schema": "metric"}

    collected_at             = Column(DateTime(timezone=True), primary_key=True)
    database_id              = Column(BigInteger, ForeignKey("metadata.database.id", ondelete="CASCADE"), primary_key=True)
    pid                      = Column(Integer, primary_key=True)
    leader_pid               = Column(Integer, nullable=True)
    usesysid                 = Column(OID, nullable=True)
    user_name                = Column(Text, nullable=True)
    application_name         = Column(Text, nullable=True)
    client_addr              = Column(INET, nullable=True)
    client_hostname          = Column(Text, nullable=True)
    client_port              = Column(Integer, nullable=True)
    backend_start            = Column(DateTime(timezone=True), primary_key=True)
    xact_start               = Column(DateTime(timezone=True), nullable=True)
    query_start              = Column(DateTime(timezone=True), nullable=True)
    state_change             = Column(DateTime(timezone=True), nullable=True)
    wait_event_type          = Column(Text, nullable=True)
    wait_event               = Column(Text, nullable=True)
    state                    = Column(Text, nullable=True)
    backend_xid              = Column(Text, nullable=True)
    backend_xmin             = Column(Text, nullable=True)
    query_id                 = Column(BigInteger, nullable=True)
    backend_type             = Column(Text, nullable=True)
    query                    = Column(Text, nullable=True)
    query_hash               = Column(Text, nullable=True)
    query_duration_ms        = Column(Float, nullable=True)
    transaction_duration_ms  = Column(Float, nullable=True)
    backend_duration_ms      = Column(Float, nullable=True)
