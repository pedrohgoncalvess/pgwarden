from sqlalchemy import BigInteger, Column, ForeignKey, Integer

from analytics.database.models.base_model import Base


class IndexColumn(Base):
    __tablename__ = "index_column"
    __table_args__ = {"schema": "metadata"}

    index_id = Column(BigInteger, ForeignKey("metadata.index.id", ondelete="CASCADE"), primary_key=True)
    column_id = Column(BigInteger, ForeignKey("metadata.column.id", ondelete="CASCADE"), primary_key=True)
    ordinal_position = Column(Integer, nullable=False)
