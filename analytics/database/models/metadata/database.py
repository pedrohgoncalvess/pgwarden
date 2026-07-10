from sqlalchemy import BigInteger, Boolean, Column, DateTime, Text

from analytics.database.models.base_model import Base


class Database(Base):
    __tablename__ = "database"
    __table_args__ = {"schema": "metadata"}

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    server_id = Column(BigInteger, nullable=False)
    db_name = Column(Text, nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    deleted_at = Column(DateTime(timezone=True), nullable=True)
