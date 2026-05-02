from sqlalchemy import Column, BigInteger, ForeignKey, DateTime, func, UniqueConstraint
from database.models.base_model import Base

class DatabaseTag(Base):
    __tablename__ = "database_tag"
    __table_args__ = (
        UniqueConstraint("database_doc_id", "tag_id"),
        {"schema": "doc"}
    )

    id              = Column(BigInteger, primary_key=True, autoincrement=True)
    database_doc_id = Column(BigInteger, ForeignKey("doc.database.id", ondelete="CASCADE"), nullable=False)
    tag_id          = Column(BigInteger, ForeignKey("doc.tag.id", ondelete="CASCADE"), nullable=False)
    created_at      = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

class SchemaTag(Base):
    __tablename__ = "schema_tag"
    __table_args__ = (
        UniqueConstraint("schema_doc_id", "tag_id"),
        {"schema": "doc"}
    )

    id              = Column(BigInteger, primary_key=True, autoincrement=True)
    schema_doc_id   = Column(BigInteger, ForeignKey("doc.schema.id", ondelete="CASCADE"), nullable=False)
    tag_id          = Column(BigInteger, ForeignKey("doc.tag.id", ondelete="CASCADE"), nullable=False)
    created_at      = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

class TableTag(Base):
    __tablename__ = "table_tag"
    __table_args__ = (
        UniqueConstraint("table_doc_id", "tag_id"),
        {"schema": "doc"}
    )

    id              = Column(BigInteger, primary_key=True, autoincrement=True)
    table_doc_id    = Column(BigInteger, ForeignKey("doc.table.id", ondelete="CASCADE"), nullable=False)
    tag_id          = Column(BigInteger, ForeignKey("doc.tag.id", ondelete="CASCADE"), nullable=False)
    created_at      = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

class ColumnTag(Base):
    __tablename__ = "column_tag"
    __table_args__ = (
        UniqueConstraint("column_doc_id", "tag_id"),
        {"schema": "doc"}
    )

    id              = Column(BigInteger, primary_key=True, autoincrement=True)
    column_doc_id   = Column(BigInteger, ForeignKey("doc.column.id", ondelete="CASCADE"), nullable=False)
    tag_id          = Column(BigInteger, ForeignKey("doc.tag.id", ondelete="CASCADE"), nullable=False)
    created_at      = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

class IndexTag(Base):
    __tablename__ = "index_tag"
    __table_args__ = (
        UniqueConstraint("index_doc_id", "tag_id"),
        {"schema": "doc"}
    )

    id              = Column(BigInteger, primary_key=True, autoincrement=True)
    index_doc_id    = Column(BigInteger, ForeignKey("doc.index.id", ondelete="CASCADE"), nullable=False)
    tag_id          = Column(BigInteger, ForeignKey("doc.tag.id", ondelete="CASCADE"), nullable=False)
    created_at      = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
