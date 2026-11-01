from sqlalchemy import (
    Column, Integer, String,
    Boolean, DateTime, func, Text, BigInteger
)
from sqlalchemy.orm import relationship

from database.models.base_model import Base


class User(Base):
    __tablename__ = "user"
    __table_args__ = {"schema": "base"}

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(50), nullable=False)
    email = Column(String(100), nullable=False, unique=True, index=True)
    password = Column(Text, nullable=False)
    is_admin = Column(Boolean, nullable=False, default=False)
    role_id = Column(BigInteger, nullable=True)
    inserted_at = Column(DateTime, nullable=False, default=func.now())
    deleted_at = Column(DateTime, nullable=True)

    refresh_tokens = relationship(
        "Refresh",
        back_populates="user",
        cascade="all, delete-orphan"
    )
