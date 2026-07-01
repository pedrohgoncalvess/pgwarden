from sqlalchemy import Column, BigInteger, ForeignKey, DateTime, Text, func, UniqueConstraint
from database.models.base_model import Base

class DatabaseDocTag(Base):
    __tablename__ = "database_doc_tag"
    __table_args__ = (
        UniqueConstraint("database_doc_id", "tag_id"),
        {"schema": "doc"}
    )

    id              = Column(BigInteger, primary_key=True, autoincrement=True)
    database_doc_id = Column(BigInteger, ForeignKey("doc.database.id", ondelete="CASCADE"), nullable=False)
    tag_id          = Column(BigInteger, ForeignKey("doc.tag.id", ondelete="CASCADE"), nullable=False)
    created_at      = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

class SchemaDocTag(Base):
    __tablename__ = "schema_doc_tag"
    __table_args__ = (
        UniqueConstraint("schema_doc_id", "tag_id"),
        {"schema": "doc"}
    )

    id              = Column(BigInteger, primary_key=True, autoincrement=True)
    schema_doc_id   = Column(BigInteger, ForeignKey("doc.schema.id", ondelete="CASCADE"), nullable=False)
    tag_id          = Column(BigInteger, ForeignKey("doc.tag.id", ondelete="CASCADE"), nullable=False)
    created_at      = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

class TableDocTag(Base):
    __tablename__ = "table_doc_tag"
    __table_args__ = (
        UniqueConstraint("table_doc_id", "tag_id"),
        {"schema": "doc"}
    )

    id              = Column(BigInteger, primary_key=True, autoincrement=True)
    table_doc_id    = Column(BigInteger, ForeignKey("doc.table.id", ondelete="CASCADE"), nullable=False)
    tag_id          = Column(BigInteger, ForeignKey("doc.tag.id", ondelete="CASCADE"), nullable=False)
    created_at      = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

class ColumnDocTag(Base):
    __tablename__ = "column_doc_tag"
    __table_args__ = (
        UniqueConstraint("column_doc_id", "tag_id"),
        {"schema": "doc"}
    )

    id              = Column(BigInteger, primary_key=True, autoincrement=True)
    column_doc_id   = Column(BigInteger, ForeignKey("doc.column.id", ondelete="CASCADE"), nullable=False)
    tag_id          = Column(BigInteger, ForeignKey("doc.tag.id", ondelete="CASCADE"), nullable=False)
    created_at      = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

class IndexDocTag(Base):
    __tablename__ = "index_doc_tag"
    __table_args__ = (
        UniqueConstraint("index_doc_id", "tag_id"),
        {"schema": "doc"}
    )

    id              = Column(BigInteger, primary_key=True, autoincrement=True)
    index_doc_id    = Column(BigInteger, ForeignKey("doc.index.id", ondelete="CASCADE"), nullable=False)
    tag_id          = Column(BigInteger, ForeignKey("doc.tag.id", ondelete="CASCADE"), nullable=False)
    created_at      = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

class DatabaseTag(Base):
    __tablename__ = "database_tag"
    __table_args__ = (
        UniqueConstraint("database_id", "tag_id"),
        {"schema": "doc"}
    )

    id          = Column(BigInteger, primary_key=True, autoincrement=True)
    database_id = Column(BigInteger, ForeignKey("metadata.database.id", ondelete="CASCADE"), nullable=False)
    tag_id      = Column(BigInteger, ForeignKey("doc.tag.id", ondelete="CASCADE"), nullable=False)
    created_at  = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

class TableTag(Base):
    __tablename__ = "table_tag"
    __table_args__ = (
        UniqueConstraint("table_id", "tag_id"),
        {"schema": "doc"}
    )

    id         = Column(BigInteger, primary_key=True, autoincrement=True)
    table_id   = Column(BigInteger, ForeignKey("metadata.table.id", ondelete="CASCADE"), nullable=False)
    tag_id     = Column(BigInteger, ForeignKey("doc.tag.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

class ColumnTag(Base):
    __tablename__ = "column_tag"
    __table_args__ = (
        UniqueConstraint("column_id", "tag_id"),
        {"schema": "doc"}
    )

    id         = Column(BigInteger, primary_key=True, autoincrement=True)
    column_id  = Column(BigInteger, ForeignKey("metadata.column.id", ondelete="CASCADE"), nullable=False)
    tag_id     = Column(BigInteger, ForeignKey("doc.tag.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

class IndexTag(Base):
    __tablename__ = "index_tag"
    __table_args__ = (
        UniqueConstraint("index_id", "tag_id"),
        {"schema": "doc"}
    )

    id         = Column(BigInteger, primary_key=True, autoincrement=True)
    index_id   = Column(BigInteger, ForeignKey("metadata.index.id", ondelete="CASCADE"), nullable=False)
    tag_id     = Column(BigInteger, ForeignKey("doc.tag.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

class QueryTag(Base):
    __tablename__ = "query_tag"
    __table_args__ = (
        UniqueConstraint("database_id", "query_hash", "tag_id"),
        {"schema": "doc"}
    )

    id          = Column(BigInteger, primary_key=True, autoincrement=True)
    database_id = Column(BigInteger, ForeignKey("metadata.database.id", ondelete="CASCADE"), nullable=False)
    query_hash  = Column(Text, nullable=False)
    tag_id      = Column(BigInteger, ForeignKey("doc.tag.id", ondelete="CASCADE"), nullable=False)
    created_at  = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
