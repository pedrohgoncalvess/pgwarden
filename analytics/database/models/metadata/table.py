from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Text

from analytics.database.models.base_model import Base


class Table(Base):
    __tablename__ = "table"
    __table_args__ = {"schema": "metadata"}

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    database_id = Column(BigInteger, ForeignKey("metadata.database.id", ondelete="CASCADE"), nullable=False)
    schema_name = Column(Text, nullable=False)
    name = Column(Text, nullable=False)
    deleted_at = Column(DateTime(timezone=True), nullable=True)
