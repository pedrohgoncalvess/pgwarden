from sqlalchemy import BigInteger, Boolean, Column, DateTime, ForeignKey, Text

from analytics.database.models.base_model import Base


class Index(Base):
    __tablename__ = "index"
    __table_args__ = {"schema": "metadata"}

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    database_id = Column(BigInteger, ForeignKey("metadata.database.id", ondelete="CASCADE"), nullable=False)
    table_id = Column(BigInteger, ForeignKey("metadata.table.id", ondelete="CASCADE"), nullable=False)
    name = Column(Text, nullable=False)
    type = Column(Text, nullable=False)
    definition = Column(Text, nullable=False)
    is_unique = Column(Boolean, nullable=False, default=False)
    is_primary = Column(Boolean, nullable=False, default=False)
    deleted_at = Column(DateTime(timezone=True), nullable=True)
