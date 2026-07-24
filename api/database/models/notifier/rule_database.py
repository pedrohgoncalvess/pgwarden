from sqlalchemy import (
    Column, BigInteger, Text,
    Float, ForeignKey, DateTime, func
)

from database.models.base_model import Base


class RuleDatabase(Base):
    __tablename__ = "rule_database"
    __table_args__ = {"schema": "notifier"}

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    rule_id = Column(
        BigInteger,
        ForeignKey("notifier.rule.id", ondelete="CASCADE"),
        nullable=False,
    )
    database_id = Column(
        BigInteger,
        ForeignKey("metadata.database.id", ondelete="CASCADE"),
        nullable=True,
    )
    type = Column(Text, nullable=False)
    warning = Column(Float, nullable=False)
    critical = Column(Float, nullable=False)
    direction = Column(Text, nullable=False, default="above")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
