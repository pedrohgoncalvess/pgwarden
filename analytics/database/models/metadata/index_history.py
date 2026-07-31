from sqlalchemy import BigInteger, Boolean, Column, DateTime, Text

from analytics.database.models.base_model import Base


class IndexHistory(Base):
    __tablename__ = "index_history"
    __table_args__ = {"schema": "metadata"}

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    index_id = Column(BigInteger, nullable=False)
    table_id = Column(BigInteger, nullable=False)
    name = Column(Text, nullable=False)
    type = Column(Text, nullable=False)
    definition = Column(Text, nullable=False)
    is_unique = Column(Boolean, nullable=False, default=False)
    is_primary = Column(Boolean, nullable=False, default=False)
    changed_at = Column(DateTime(timezone=True), nullable=False)
