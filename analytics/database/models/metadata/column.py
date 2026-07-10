from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Integer, Text

from analytics.database.models.base_model import Base


class ColumnModel(Base):
    __tablename__ = "column"
    __table_args__ = {"schema": "metadata"}

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    table_id = Column(BigInteger, ForeignKey("metadata.table.id", ondelete="CASCADE"), nullable=False)
    name = Column(Text, nullable=False)
    data_type = Column(Text, nullable=False)
    ordinal_position = Column(Integer, nullable=False)
    fk_table_id = Column(BigInteger, ForeignKey("metadata.table.id", ondelete="SET NULL"), nullable=True)
    fk_column_id = Column(BigInteger, ForeignKey("metadata.column.id", ondelete="SET NULL"), nullable=True)
    deleted_at = Column(DateTime(timezone=True), nullable=True)
